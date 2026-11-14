"""Servidor da Concilia AI: API + telas. Rode com:  uvicorn app.main:app --port 8000"""
import csv
import io
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from urllib.parse import quote

import pymupdf as fitz
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from .classificacao_subtipos import SUBTIPOS, ROTULOS_SUBTIPOS

from . import (
    analise,
    anonimizar,
    auth,
    avaliacao,
    conciliacao,
    config,
    db,
    fiscal,
    pipeline,
    seed,
)
from . import arquivos as armazenamento
from .fiscal import brl, fmt_cnpj, fmt_data
from .integrations.admin import router as integracoes_router
from .integrations.erp import router as erp_router

trabalhador = pipeline.Trabalhador()
MAX_MB = config.MAX_MB  # por arquivo (CONCILIA_MAX_MB no .env); lotes digitalizados costumam ter dezenas de MB
MAX_BYTES = MAX_MB * 1024 * 1024
PUBLICAS = {"/api/login", "/api/estado", "/api/sair", "/api/contas"}

# De qual workspace é cada recurso pedido pelo caminho: o middleware confere se ele é da conta do usuário.
_DONO = [
    (re.compile(r"^/api/ws/([^/]+)"), None),
    (re.compile(r"^/api/docs/(\d+)"), "SELECT ws FROM docs WHERE id=?"),
    (re.compile(r"^/api/envios/(\d+)"), "SELECT ws FROM envios WHERE id=?"),
    (re.compile(r"^/api/notas/(\d+)"), "SELECT ws FROM notas WHERE id=?"),
    (re.compile(r"^/api/divergencias/(\d+)"), "SELECT ws FROM divergencias WHERE id=?"),
    (re.compile(r"^/api/documentos-fiscais/(\d+)"), "SELECT ws FROM documentos_fiscais WHERE id=?"),
    (re.compile(r"^/api/paginas/(\d+)"), "SELECT e.ws FROM paginas p JOIN envios e ON e.id=p.envio_id WHERE p.id=?"),
    (re.compile(r"^/api/integracoes/(\d+)"), "SELECT ws FROM integracoes WHERE id=?"),
]


def _workspace_do_caminho(caminho: str) -> str | None:
    for padrao, sql in _DONO:
        m = padrao.match(caminho)
        if m:
            if sql is None:
                return m.group(1)
            r = db.q(sql, (int(m.group(1)),), um=True)
            return r["ws"] if r else None
    return None


def workspace_da_conta(ws: str, conta_id: str) -> bool:
    return bool(db.q("SELECT 1 FROM workspaces WHERE id=? AND conta_id=?", (ws, conta_id)))


@asynccontextmanager
async def vida(app):
    seed.semear()
    auth.criar_usuarios_padrao()
    if not trabalhador.is_alive():
        trabalhador.start()
    yield


app = FastAPI(title="Concilia AI", lifespan=vida)
app.include_router(integracoes_router)
app.include_router(erp_router)


@app.middleware("http")
async def exigir_login(request: Request, chamar):
    if (request.url.path.startswith("/api/")
            and request.url.path not in PUBLICAS
            and not request.url.path.startswith("/api/erp/v1/")):
        u = auth.usuario_da_requisicao(request)
        conta = auth.conta_do_usuario(u["usuario"]) if u else None
        if not u or not conta:
            return JSONResponse({"detail": "Entre na sua conta para continuar."}, status_code=401)
        u = {**u, "conta_id": conta}
        request.state.usuario = u
        # Isolamento entre empresas: workspace de outra conta responde como se não existisse.
        ws = _workspace_do_caminho(request.url.path)
        if ws and not workspace_da_conta(ws, conta):
            return JSONResponse({"detail": "Não encontrado."}, status_code=404)
    return await chamar(request)


@app.post("/api/login")
def login(corpo: dict):
    token, u = auth.entrar(corpo.get("usuario"), corpo.get("senha"))  # valida tipos e tentativas
    r = JSONResponse(u)
    r.set_cookie(auth.COOKIE, token, max_age=auth.DURACAO, httponly=True, samesite="lax")
    return r


@app.post("/api/contas")
def criar_conta(corpo: dict):
    """Cadastro de uma empresa nova: cria a conta e o primeiro usuário (administrador) e já entra."""
    if not config.CADASTRO_ABERTO:
        raise HTTPException(403, "O cadastro de contas está fechado neste servidor.")
    empresa = corpo.get("empresa")
    if not isinstance(empresa, str) or not 2 <= len(empresa.strip()) <= 120:
        raise HTTPException(400, "Informe o nome da empresa.")
    # Confere tudo antes de gravar: um cadastro recusado não deixa conta pela metade.
    auth.validar_usuario(corpo.get("usuario"), corpo.get("nome"), corpo.get("senha"), "admin")
    cid = seed.criar_conta(empresa.strip())
    try:
        publico = auth.criar_usuario(cid, corpo.get("usuario"), corpo.get("nome"), corpo.get("senha"), "admin")
    except Exception:
        db.x("DELETE FROM contas WHERE id=?", (cid,))  # ex.: o mesmo usuário cadastrado ao mesmo tempo
        raise
    r = JSONResponse({**publico, "conta": {"id": cid, "nome": empresa.strip()}})
    r.set_cookie(auth.COOKIE, auth.sessao_para(publico), max_age=auth.DURACAO, httponly=True, samesite="lax")
    return r


@app.get("/api/usuarios")
def usuarios_da_conta(request: Request):
    u = auth.exigir(request, "admin")
    return db.q("SELECT usuario, nome, perfil FROM usuarios WHERE conta_id=? ORDER BY nome", (u["conta_id"],))


@app.post("/api/usuarios")
def cadastrar_usuario(request: Request, corpo: dict):
    """O administrador da conta cadastra outra pessoa da empresa."""
    u = auth.exigir(request, "admin")
    return auth.criar_usuario(u["conta_id"], corpo.get("usuario"), corpo.get("nome"), corpo.get("senha"),
                              corpo.get("perfil") or "operador")


def documentos_da_conta(conta_id: str) -> int:
    return db.q("SELECT COUNT(*) c FROM docs WHERE ws IN (SELECT id FROM workspaces WHERE conta_id=?)",
                (conta_id,), um=True)["c"]


def _limite_documentos(ws: str):
    """Até config.LIMITE_DOCUMENTOS documentos por conta, somando todos os workspaces dela."""
    conta = db.q("SELECT conta_id FROM workspaces WHERE id=?", (ws,), um=True)
    if conta and documentos_da_conta(conta["conta_id"]) >= config.LIMITE_DOCUMENTOS:
        limite = f"{config.LIMITE_DOCUMENTOS:,}".replace(",", ".")
        raise HTTPException(403, f"A conta chegou ao limite de {limite} documentos. "
                                 "Exclua documentos antigos ou fale com a gente para ampliar.")


@app.post("/api/sair")
def sair(request: Request):
    auth.sair(request)
    r = JSONResponse({"ok": True})
    r.delete_cookie(auth.COOKIE)
    return r


def _ws(ws):
    w = db.q("SELECT * FROM workspaces WHERE id=?", (ws,), um=True)
    if not w:
        raise HTTPException(404, "Cliente não encontrado")
    return w


def _doc(did):
    d = db.q("SELECT * FROM docs WHERE id=?", (did,), um=True)
    if not d:
        raise HTTPException(404, "Documento não encontrado")
    return d


def _cats(ws):
    return anonimizar.ativos(db.get_config(ws))


def _j(v, padrao):
    try:
        return json.loads(v) if v else padrao
    except Exception:
        return padrao


def _doc_publico(d, cats, com_paginas=False):
    out = {k: d[k] for k in ("id", "envio_id", "tipo", "conf", "pag_ini", "pag_fim", "empresa", "status",
                             "duvida", "motivo", "decisao", "criado_em")}
    out["pessoa"] = d["pessoa"]
    out["cpf"] = anonimizar.mascarar_texto(d["cpf"] or "", cats) if d["cpf"] else None
    out["sinais"] = _j(d["sinais"], [])
    out["candidatos"] = _j(d["candidatos"], [])
    out["subtipo"] = d.get("subtipo") or "nao_identificado"
    out["subtipo_rotulo"] = ROTULOS_SUBTIPOS.get(out["subtipo"], "Não identificado")
    out["subtipo_pontos"] = d.get("subtipo_pontos")
    out["subtipo_evidencias"] = _j(d.get("subtipo_evidencias"), [])
    out["subtipo_alternativas"] = _j(d.get("subtipo_alternativas"), [])
    out["subtipo_revisao"] = bool(d.get("subtipo_revisao", 1))
    out["subtipo_manual"] = bool(d.get("subtipo_manual"))
    out["dados"] = _j(d.get("dados"), None)
    out["aviso"] = d.get("aviso")
    if com_paginas:
        out["paginas"] = db.q("SELECT id, n, tipo, conf, inicio FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n",
                              (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    return out


# ------------------------------------------------------------------ telas
# O front novo (frontend/dist, montado pelo iniciar.bat/iniciar.sh) é servido pela própria API em
# http://127.0.0.1:8000: um endereço só, sem npm run dev nem certificado. Sem ele, abre a versão anterior (web/).
FRONT_PRONTO = config.BASE / "frontend" / "dist"


@app.get("/")
def tela():
    # Sem cache: depois de atualizar o sistema, o navegador sempre pega as telas novas.
    pagina = FRONT_PRONTO / "index.html"
    return FileResponse(pagina if pagina.exists() else config.WEB / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/estado")
def estado(request: Request):
    u = auth.usuario_da_requisicao(request)
    conta_id = auth.conta_do_usuario(u["usuario"]) if u else None
    conta = db.q("SELECT id, nome FROM contas WHERE id=?", (conta_id,), um=True) if conta_id else None
    if not conta:
        u = None
    return {
        "claude_configurado": config.claude_configurado(),
        "modelo": config.MODELO,
        "cadastro_aberto": config.CADASTRO_ABERTO,
        "usuario": {k: u[k] for k in ("usuario", "nome", "perfil")} if u else None,
        "conta": {**conta, "documentos": documentos_da_conta(conta_id),
                  "limite_documentos": config.LIMITE_DOCUMENTOS} if u else None,
        # Só os workspaces (clientes) da conta de quem entrou.
        "clientes": db.q("SELECT * FROM workspaces WHERE conta_id=? ORDER BY ordem", (conta_id,)) if u else [],
    }


# ------------------------------------------------------------------ início
@app.get("/api/ws/{ws}/resumo")
def resumo(ws: str):
    _ws(ws)
    def conta(sql, args=()):
        return db.q(sql, (ws, *args), um=True)["c"]
    notas = conta("SELECT COUNT(*) c FROM notas WHERE ws=?")
    por_status = {r["status"]: r["c"] for r in db.q("SELECT status, COUNT(*) c FROM notas WHERE ws=? GROUP BY status", (ws,))}
    valor_total = db.q("SELECT COALESCE(SUM(valor),0) v FROM notas WHERE ws=?", (ws,), um=True)["v"]
    em_risco = db.q("SELECT COALESCE(SUM(valor),0) v FROM notas WHERE ws=? AND status IN ('divergente','rejeitada')", (ws,), um=True)["v"]
    abertas = db.q("""SELECT d.*, n.numero, n.nome_prestador, n.cnpj_prestador, n.valor FROM divergencias d
                      JOIN notas n ON n.id=d.nota_id WHERE d.ws=? AND d.status='aberta'
                      ORDER BY CASE d.severidade WHEN 'critica' THEN 0 WHEN 'alta' THEN 1 ELSE 2 END, d.id LIMIT 6""", (ws,))
    for d in abertas:
        d["titulo"] = conciliacao.REGRAS[d["regra"]][0]
    pend = conta("SELECT COUNT(*) c FROM docs WHERE ws=? AND status='revisao'")
    ativo = db.q("SELECT * FROM envios WHERE ws=? AND status IN ('fila','processando','pausado','falhou') ORDER BY id DESC LIMIT 1", (ws,), um=True)
    return {"notas": notas, "conciliadas": por_status.get("conciliada", 0) + por_status.get("aprovada", 0),
            "divergentes": por_status.get("divergente", 0), "rejeitadas": por_status.get("rejeitada", 0),
            "div_abertas": conta("SELECT COUNT(*) c FROM divergencias WHERE ws=? AND status='aberta'"),
            "valor_total": valor_total, "valor_risco": em_risco,
            "contratos": conta("SELECT COUNT(*) c FROM contratos WHERE ws=?"),
            "fornecedores": conta("SELECT COUNT(*) c FROM fornecedores WHERE ws=?"),
            "pendencias": pend, "ativo": ativo, "alertas": abertas,
            "envios": db.q("SELECT * FROM envios WHERE ws=? ORDER BY id DESC LIMIT 5", (ws,))}


@app.get("/api/ws/{ws}/visao")
def visao(ws: str):
    """Números das 5 etapas: ingestão, identificação, classificação, validação e disponibilização."""
    _ws(ws)
    def um(sql, args=()):
        return db.q(sql, (ws, *args), um=True)["c"] or 0
    tipos = db.q("SELECT tipo, COUNT(*) c FROM docs WHERE ws=? GROUP BY tipo ORDER BY c DESC", (ws,))
    docs = um("SELECT COUNT(*) c FROM docs WHERE ws=?")
    auto = um("SELECT COUNT(*) c FROM docs WHERE ws=? AND status='confirmado' AND decisao IS NULL")
    return {
        "envios": um("SELECT COUNT(*) c FROM envios WHERE ws=?"),
        "arquivos": um("SELECT COUNT(*) c FROM arquivos WHERE ws=?"),
        "paginas": um("SELECT COALESCE(SUM(feitas),0) c FROM envios WHERE ws=?"),
        "documentos": docs, "tipos": tipos,
        "automaticos": auto, "pct_auto": round(100 * auto / docs) if docs else None,
        "revisao": um("SELECT COUNT(*) c FROM docs WHERE ws=? AND status='revisao'"),
        "decididos": um("SELECT COUNT(*) c FROM docs WHERE ws=? AND decisao IS NOT NULL"),
        "prontos": um("SELECT COUNT(*) c FROM docs WHERE ws=? AND status='confirmado'"),
        "retomadas": um("SELECT COALESCE(SUM(retomadas),0) c FROM envios WHERE ws=?"),
        "ativos": db.q("SELECT * FROM envios WHERE ws=? AND status IN ('fila','processando','pausado','falhou','recebendo') ORDER BY id DESC", (ws,)),
        "recentes": db.q("SELECT * FROM envios WHERE ws=? ORDER BY id DESC LIMIT 5", (ws,)),
    }


@app.get("/api/ws/{ws}/contagens")
def contagens(ws: str):
    """Números do menu lateral."""
    return {"pendencias": db.q("SELECT COUNT(*) c FROM docs WHERE ws=? AND status='revisao'", (ws,), um=True)["c"],
            "divergencias": db.q("SELECT COUNT(*) c FROM divergencias WHERE ws=? AND status='aberta'", (ws,), um=True)["c"]}


# ------------------------------------------------------------------ envios
@app.post("/api/ws/{ws}/envios")
async def enviar(request: Request, ws: str, arquivos: list[UploadFile] = File(...), origem: str = Form("")):
    _ws(ws)
    u = auth.exigir(request, "operador")
    _limite_documentos(ws)
    dados = []
    for a in arquivos:
        conteudo = await a.read(MAX_BYTES + 1)
        if len(conteudo) > MAX_BYTES:
            raise HTTPException(413, f"“{a.filename}” passa de {MAX_MB} MB. Divida o arquivo e envie de novo.")
        dados.append((a.filename or "arquivo", conteudo))
    eid = pipeline.criar_envio(ws, dados, origem or f"Enviado por {u['nome']}", usuario=u["usuario"])
    trabalhador.acordar.set()
    return db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)


def _lote_sintetico(ws: str, u: dict, origem: str, fornecedores: int = 4, digitalizar: bool = True):
    """Gera contratos, aditivos e notas fictícios (com gabarito) e envia: o PDF misturado + o XML de cada nota."""
    pasta = avaliacao.gerar_lote(fornecedores=fornecedores, notas=3, digitalizar=digitalizar)
    gab = json.loads((pasta / "ground_truth.json").read_text(encoding="utf-8"))
    nomes = {s["cnpj"]: s["razao_social"] for s in gab["suppliers"]}
    lote = pasta / "lotes" / "lote_misturado.pdf"
    if digitalizar:  # o lote inteiro vira imagem (TIFF), como sai do scanner: tudo passa por OCR
        lote = avaliacao.digitalizar(lote, pasta / "lotes" / "lote_digitalizado.tif")
    arquivos = [(lote.name, lote.read_bytes())]
    for inv in gab["invoices"]:
        nome = nomes.get(inv["prestador_cnpj"], "Prestador sem contrato ME")
        arquivos.append((f"NFSe-{inv['numero']}-{inv['invoice_id']}.xml", fiscal.nfse_nacional_xml(inv, nome)))
    eid = pipeline.criar_envio(ws, arquivos, origem, usuario=u["usuario"], permitir_repetido=True)
    db.x("UPDATE envios SET gabarito=?, nome=? WHERE id=?",
         (str(pasta / "ground_truth.json"), f"Lote fictício: {len(gab['invoices'])} XML de NFS-e + {'TIFF digitalizado' if digitalizar else 'PDF'} "
          f"de {gab['batch_total_pages']} páginas ({lote.stat().st_size / 1e6:.0f} MB)", eid))
    trabalhador.acordar.set()
    return db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)


@app.post("/api/ws/{ws}/exemplo")
def enviar_exemplo(request: Request, ws: str):
    """Envia um lote fictício de contratos, aditivos e notas (para demonstração)."""
    _ws(ws)
    u = auth.exigir(request, "operador")
    _limite_documentos(ws)
    # 7 fornecedores: o mínimo para o lote ter todos os cenários de divergência do gerador.
    return _lote_sintetico(ws, u, "Lote de exemplo com gabarito", 7)


@app.post("/api/ws/{ws}/avaliacao")
def nova_avaliacao(request: Request, ws: str, corpo: dict | None = None):
    """Gera um lote sintético com gabarito e envia para medir o acerto da IA."""
    _ws(ws)
    u = auth.exigir(request, "admin")
    corpo = corpo or {}
    try:
        fornecedores = max(7, min(20, int(corpo.get("fornecedores", 8))))
    except (TypeError, ValueError):
        raise HTTPException(400, "Informe o número de fornecedores (de 7 a 20).") from None
    return _lote_sintetico(ws, u, "Avaliação com gabarito", fornecedores, bool(corpo.get("digitalizar", True)))


@app.get("/api/ws/{ws}/avaliacoes")
def avaliacoes(ws: str):
    out = []
    for e in db.q("SELECT * FROM envios WHERE ws=? AND gabarito IS NOT NULL ORDER BY id DESC", (ws,)):
        out.append({"envio": e, "resultado": avaliacao.medir_envio(e["id"])})
    return out


@app.get("/api/ws/{ws}/envios")
def envios(ws: str):
    # Com o resultado de cada envio (documentos separados e quantos ficaram para a revisão humana).
    return db.q("""SELECT e.*, (SELECT COUNT(*) FROM docs d WHERE d.envio_id=e.id) documentos,
                   (SELECT COUNT(*) FROM docs d WHERE d.envio_id=e.id AND d.status='revisao') duvidas
                   FROM envios e WHERE e.ws=? ORDER BY e.id DESC""", (ws,))


@app.get("/api/envios/{eid}")
def envio(eid: int):
    e = db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)
    if not e:
        raise HTTPException(404, "Envio não encontrado")
    cats = _cats(e["ws"])
    pags = db.q("SELECT id, n, status, tipo, conf, inicio, sinais, doc_id, motor, fonte_texto FROM paginas WHERE envio_id=? ORDER BY n", (eid,))
    for p in pags:
        p["sinais"] = _j(p["sinais"], [])
    docs = [_doc_publico(d, cats) for d in db.q("SELECT * FROM docs WHERE envio_id=? ORDER BY pag_ini", (eid,))]
    notas = db.q("SELECT id, numero, nome_prestador, cnpj_prestador, valor, status, origem FROM notas WHERE envio_id=? ORDER BY id", (eid,))
    fiscais = db.q("""SELECT id, modelo, tipo, numero, chave, emissor, criado_em
                       FROM documentos_fiscais WHERE envio_id=? ORDER BY id""", (eid,))
    return {"envio": e, "paginas": pags, "docs": docs, "notas": notas, "fiscais": fiscais,
            "eventos": db.q("SELECT * FROM eventos WHERE envio_id=? ORDER BY id", (eid,))}


@app.post("/api/envios/{eid}/pausar")
def pausar(request: Request, eid: int):
    auth.exigir(request, "operador")
    db.x("UPDATE envios SET status='pausado' WHERE id=? AND status IN ('fila','processando')", (eid,))
    return {"ok": True}


@app.post("/api/envios/{eid}/retomar")
def retomar(request: Request, eid: int):
    u = auth.exigir(request, "operador")
    ok = pipeline.retomar_envio(eid, f"Retomado por {u['nome']}")
    trabalhador.acordar.set()
    return {"ok": ok}


@app.post("/api/envios/{eid}/cancelar")
def cancelar(request: Request, eid: int):
    """Para a leitura de vez. As páginas já lidas ficam guardadas, mas o envio não vira documentos."""
    u = auth.exigir(request, "operador")
    e = db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)
    if not e:
        raise HTTPException(404, "Envio não encontrado")
    if e["status"] not in ("fila", "processando", "pausado", "falhou"):
        raise HTTPException(400, "Este envio já terminou e não pode ser cancelado.")
    db.x("UPDATE envios SET status='cancelado', terminado_em=? WHERE id=?", (db.agora(), eid))
    db.evento(eid, f"Cancelado por {u['nome']} na página {e['feitas'] + 1}.")
    return {"ok": True}


@app.post("/api/envios/{eid}/simular-falha")
def simular_falha(request: Request, eid: int):
    auth.exigir(request, "operador")
    db.x("UPDATE envios SET falha_simulada=1 WHERE id=?", (eid,))
    return {"ok": True}


# ------------------------------------------------------------------ páginas
REVELAR_MINUTOS = 30  # depois de pedir com motivo, o revisor vê as imagens sem máscara por este tempo


@app.get("/api/paginas/{pid}/imagem")
def imagem(request: Request, pid: int, largura: int = 0, revelar: int = 0):
    p = db.q("SELECT p.*, e.ws FROM paginas p JOIN envios e ON e.id=p.envio_id WHERE p.id=?", (pid,), um=True)
    if not p or not p["img"]:
        raise HTTPException(404, "Página ainda não processada")
    img = armazenamento.local(p["img"])
    if not img:
        raise HTTPException(404, "A imagem desta página não está disponível (nem no disco nem no Storage).")
    if revelar:
        # Imagem sem máscara só para revisor que registrou o motivo deste documento há pouco (POST /revelar).
        u = auth.exigir(request, "revisor")
        desde = (datetime.now() - timedelta(minutes=REVELAR_MINUTOS)).strftime("%Y-%m-%d %H:%M:%S")
        if not p["doc_id"] or not db.q("SELECT 1 FROM acessos WHERE doc_id=? AND usuario=? AND quando>=?",
                                       (p["doc_id"], u["nome"], desde)):
            raise HTTPException(403, "Para ver os dados protegidos, informe o motivo no documento.")
    cats = [] if revelar else _cats(p["ws"])
    # A tela do envio se atualiza a cada 1,5 s: sem guardar a imagem pronta, o servidor redesenharia
    # cada miniatura toda vez, disputando o processador com o OCR. Versão revelada não é guardada.
    import hashlib
    cache = None
    if not revelar:
        chave = hashlib.sha1(json.dumps([sorted(cats), p["sensiveis"] or ""]).encode()).hexdigest()[:10]
        cache = config.DADOS / "miniaturas" / f"{pid}_{largura}_{chave}.jpg"
        if cache.exists():
            return Response(cache.read_bytes(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})
    im = anonimizar.mascarar_imagem(img, _j(p["linhas"], []), cats, _j(p["sensiveis"], []))
    if largura:
        im.thumbnail((largura, largura * 2))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, "JPEG", quality=82)
    if cache:
        cache.parent.mkdir(exist_ok=True)
        cache.write_bytes(buf.getvalue())
        return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "private, max-age=300"})
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ pendências (dúvidas da leitura)
@app.get("/api/ws/{ws}/pendencias")
def pendencias(ws: str):
    cats = _cats(ws)
    out = []
    for d in db.q("SELECT * FROM docs WHERE ws=? AND (status='revisao' OR (subtipo_revisao=1 AND subtipo_manual=0)) ORDER BY id", (ws,)):
        doc = _doc_publico(d, cats, com_paginas=True)
        # Mostra uma página antes e uma depois para decidir fronteiras.
        doc["vizinhas"] = db.q("SELECT id, n, tipo, doc_id FROM paginas WHERE envio_id=? AND n IN (?,?) ORDER BY n",
                               (d["envio_id"], d["pag_ini"] - 1, d["pag_fim"] + 1))
        out.append(doc)
    tipos = [t["nome"] for t in db.tipos_ws(ws)]
    return {"pendencias": out, "tipos": tipos, "subtipos": ROTULOS_SUBTIPOS,
            "limiar": int(db.get_config(ws)["limiar"])}


@app.post("/api/docs/{did}/decisao")
def decisao(request: Request, did: int, corpo: dict):
    u = auth.exigir(request, "revisor")
    ws = _doc(did)["ws"]
    resultado = _decidir(did, corpo)
    if corpo.get("acao") == "corrigir_subtipo":
        db.trilha(ws, u["nome"], f"corrigiu o subtipo do documento #{did} para {corpo.get('subtipo')}")
    if db.q("SELECT 1 FROM docs WHERE id=?", (did,)):
        db.x("UPDATE docs SET decidido_por=? WHERE id=?", (u["nome"], did))
    # Documento confirmado: lê os campos e refaz o cruzamento com as notas.
    for d in db.q("""SELECT id FROM docs WHERE ws=? AND status='confirmado'
                     AND (dados IS NULL OR dados LIKE '%"provisorio": true%')""", (ws,)):
        conciliacao.extrair_doc(d["id"])
    conciliacao.conciliar(ws)
    return resultado


def _limpar_extraidos(did: int):
    """Tira da conferência o que foi lido deste documento: notas em PDF (e suas divergências), contratos e
    aditivos. Notas vindas do XML continuam, só perdem o vínculo com o PDF."""
    for nota in db.q("SELECT id FROM notas WHERE doc_id=? AND origem='pdf'", (did,)):
        db.x("DELETE FROM divergencias WHERE nota_id=?", (nota["id"],))
        db.x("DELETE FROM notas WHERE id=?", (nota["id"],))
    db.x("UPDATE notas SET doc_id=NULL WHERE doc_id=?", (did,))
    db.x("DELETE FROM contratos WHERE doc_id=?", (did,))
    db.x("DELETE FROM aditivos WHERE doc_id=?", (did,))


def _decidir(did: int, corpo: dict):
    d = _doc(did)
    acao = corpo.get("acao")
    agora = db.agora()
    if acao == "corrigir_subtipo":
        subtipo = corpo.get("subtipo")
        if subtipo not in SUBTIPOS:
            raise HTTPException(400, "Subtipo inválido")
        # Atualização de subtipo é independente da aprovação do documento,
        # que continua sujeita aos fluxos normais de revisão.
        db.x("""UPDATE docs SET subtipo=?, subtipo_pontos=NULL, subtipo_evidencias=?,
               subtipo_alternativas='[]', subtipo_revisao=0, subtipo_manual=1
               WHERE id=?""",
             (subtipo, json.dumps(["Subtipo corrigido por revisão humana"], ensure_ascii=False), did))
        return {"ok": True, "msg": f"Subtipo registrado: {ROTULOS_SUBTIPOS[subtipo]}."}
    if acao == "confirmar":
        tipo = corpo.get("tipo") or d["tipo"]
        if tipo != d["tipo"]:
            _limpar_extraidos(did)  # ex.: era Contrato e virou Aditivo: o contrato lido antes não vale mais
        db.x("UPDATE docs SET tipo=?, status='confirmado', decisao=?, decidido_em=?, dados=NULL WHERE id=?",
             (tipo, f"Confirmado como {tipo}", agora, did))
        if tipo != d["tipo"]:
            pipeline.atualizar_subtipo(did, forcar=True)
        pipeline.aprender(d["ws"], tipo, did)
        return {"ok": True, "msg": f"Confirmado como {tipo}."}
    if acao == "dividir":
        n = int(corpo.get("pagina", 0))
        if not (d["pag_ini"] < n <= d["pag_fim"]):
            raise HTTPException(400, "Escolha uma página do meio do documento para começar o novo.")
        p = db.q("SELECT * FROM paginas WHERE envio_id=? AND n=?", (d["envio_id"], n), um=True)
        db.x("UPDATE paginas SET inicio=1 WHERE id=?", (p["id"],))
        db.x("UPDATE docs SET pag_fim=?, status='confirmado', decisao=?, decidido_em=?, dados=NULL WHERE id=?",
             (n - 1, f"Dividido na página {n}", agora, did))
        tipo_novo = corpo.get("tipo") or p["tipo"] or d["tipo"]
        novo = db.x("""INSERT INTO docs(envio_id, ws, tipo, conf, pag_ini, pag_fim, pessoa, cpf, empresa, status, duvida,
                    motivo, sinais, candidatos, sensiveis, criado_em, decidido_em, decisao)
                    VALUES(?,?,?,?,?,?,?,?,?,'confirmado','tipo',?,?,?,?,?,?,?)""",
                    (d["envio_id"], d["ws"], tipo_novo, p["conf"], n, d["pag_fim"], p["pessoa"] or d["pessoa"],
                     p["cpf"] or d["cpf"], p["empresa"] or d["empresa"], f"página {n}", p["sinais"], p["candidatos"],
                     p["sensiveis"], agora, agora, f"Separado do documento #{did}"))
        pipeline.reindexar_doc(did)
        pipeline.reindexar_doc(novo)
        return {"ok": True, "msg": f"Pronto. Virou dois documentos, o segundo começa na página {n}."}
    if acao == "juntar":
        ant = db.q("SELECT * FROM docs WHERE envio_id=? AND pag_fim=?", (d["envio_id"], d["pag_ini"] - 1), um=True)
        if not ant:
            raise HTTPException(400, "Não há documento anterior para juntar.")
        db.x("UPDATE paginas SET inicio=0 WHERE envio_id=? AND n=?", (d["envio_id"], d["pag_ini"]))
        db.x("UPDATE docs SET pag_fim=?, status='confirmado', decisao=?, decidido_em=?, dados=NULL WHERE id=?",
             (d["pag_fim"], f"Juntado com as páginas {d['pag_ini']}–{d['pag_fim']}", agora, ant["id"]))
        _limpar_extraidos(did)
        db.x("DELETE FROM busca WHERE doc_id=?", (did,))
        db.x("DELETE FROM docs WHERE id=?", (did,))
        pipeline.reindexar_doc(ant["id"])
        return {"ok": True, "msg": "Pronto. Juntado ao documento anterior."}
    if acao == "pedir":
        db.x("UPDATE docs SET status='aguardando', decisao=?, decidido_em=? WHERE id=?",
             ("Nova cópia pedida", agora, did))
        return {"ok": True, "msg": "Pedido registrado. O documento fica aguardando a nova cópia."}
    if acao == "reprocessar":
        e = db.q("SELECT * FROM envios WHERE id=?", (d["envio_id"],), um=True)
        cfg = db.get_config(e["ws"])
        tipos = db.tipos_ws(e["ws"])
        ex = db.q("SELECT * FROM exemplos WHERE ws=?", (e["ws"],))
        pags = db.q("SELECT * FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n", (d["envio_id"], d["pag_ini"], d["pag_fim"]))
        confs, primeira = [], None
        for p in pags:
            anterior = db.q("SELECT tipo, pessoa, cpf FROM paginas WHERE envio_id=? AND n=?", (d["envio_id"], p["n"] - 1), um=True)
            r = analise.analisar(str(armazenamento.local(p["img"]) or ""), p["texto"], tipos, anterior, ex,
                                 cfg.get("usar_claude") == "1")
            db.x("UPDATE paginas SET tipo=?, conf=?, sinais=?, candidatos=?, motor=? WHERE id=?",
                 (r["tipo"], r["conf"], json.dumps(r["sinais"], ensure_ascii=False),
                  json.dumps(r["candidatos"], ensure_ascii=False), r["motor"], p["id"]))
            confs.append(r["conf"])
            primeira = primeira or r
        conf = min(confs)
        status = "revisao" if conf < int(cfg["limiar"]) else "confirmado"
        db.x("UPDATE docs SET tipo=?, conf=?, status=?, sinais=?, candidatos=?, decisao=?, dados=NULL WHERE id=?",
             (primeira["tipo"], conf, status, json.dumps(primeira["sinais"], ensure_ascii=False),
              json.dumps(primeira["candidatos"], ensure_ascii=False), "Reprocessado", did))
        pipeline.atualizar_subtipo(did)
        msg = "Reprocessado. Continua precisando de você." if status == "revisao" else f"Reprocessado: {primeira['tipo']}, confiança {conf}%."
        return {"ok": True, "msg": msg}
    raise HTTPException(400, "Ação desconhecida")


# ------------------------------------------------------------------ conciliação
def _nota_publica(n):
    out = dict(n)
    out.pop("xml", None)
    out["cnpj_fmt"] = fmt_cnpj(n["cnpj_prestador"])
    return out


@app.get("/api/ws/{ws}/divergencias")
def divergencias(ws: str, status: str = "aberta"):
    _ws(ws)
    filtro = "" if status == "todas" else "AND d.status=?"
    args = (ws,) if status == "todas" else (ws, status)
    L = db.q(f"""SELECT d.*, n.numero, n.nome_prestador, n.cnpj_prestador, n.valor, n.data_emissao, n.descricao,
                 n.origem, n.doc_id nota_doc_id, c.numero contrato_numero, c.objeto, c.valor_mensal, c.vigencia_inicio,
                 c.vigencia_fim, c.doc_id contrato_doc_id,
                 (SELECT MAX(quando) FROM avisos a WHERE a.divergencia_id=d.id) avisado_em
                 FROM divergencias d JOIN notas n ON n.id=d.nota_id LEFT JOIN contratos c ON c.id=d.contrato_id
                 WHERE d.ws=? {filtro}
                 ORDER BY CASE d.status WHEN 'aberta' THEN 0 ELSE 1 END,
                          CASE d.severidade WHEN 'critica' THEN 0 WHEN 'alta' THEN 1 ELSE 2 END, d.id""", args)
    for d in L:
        d["titulo"] = conciliacao.REGRAS[d["regra"]][0]
        d["cnpj_fmt"] = fmt_cnpj(d["cnpj_prestador"])
    contagem = {r["status"]: r["c"] for r in db.q("SELECT status, COUNT(*) c FROM divergencias WHERE ws=? GROUP BY status", (ws,))}
    return {"divergencias": L, "contagem": contagem}


@app.post("/api/divergencias/{did}/decisao")
def decidir_divergencia(request: Request, did: int, corpo: dict):
    u = auth.exigir(request, "revisor")
    acao = corpo.get("acao")
    comentario = (corpo.get("comentario") or "").strip()
    if acao == "rejeitar" and len(comentario) < 3:
        raise HTTPException(400, "Escreva o motivo da rejeição. Ele vai para o relatório do fornecedor.")
    try:
        r = conciliacao.decidir(did, acao, comentario, u["nome"])
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    r["msg"] = {"aprovada": "Aprovada. A nota segue para pagamento.", "rejeitada": "Rejeitada. Fica registrada para cobrar o fornecedor.",
                "aberta": "Reaberta. Voltou para a fila."}[r["status"]]
    return r


@app.post("/api/divergencias/{did}/aviso")
def avisar_fornecedor(request: Request, did: int):
    """Monta o aviso ao fornecedor com a divergência e registra que foi gerado (quem, quando, para quem)."""
    u = auth.exigir(request, "revisor")
    d = db.q("""SELECT d.*, n.numero, n.data_emissao, n.valor, n.nome_prestador, w.nome cliente,
                f.nome forn_nome, f.email, f.responsavel
                FROM divergencias d JOIN notas n ON n.id=d.nota_id JOIN workspaces w ON w.id=d.ws
                LEFT JOIN fornecedores f ON f.id=d.fornecedor_id WHERE d.id=?""", (did,), um=True)
    if not d:
        raise HTTPException(404, "Divergência não encontrada")
    titulo = conciliacao.REGRAS[d["regra"]][0]
    nome = d["forn_nome"] or d["nome_prestador"] or "fornecedor"
    assunto = f"Nota fiscal {d['numero']}: {titulo.lower()} ({d['cliente']})"
    linhas = [f"Olá, {nome}.", "",
              f"Na conferência da nota fiscal nº {d['numero']}, emitida em {fmt_data(d['data_emissao'])} no valor de {brl(d['valor'])}, "
              f"encontramos o seguinte: {d['mensagem']}", "",
              f"O contrato prevê: {d['esperado'] or '—'}", f"A nota apresenta: {d['encontrado'] or '—'}"]
    if d["comentario"]:
        linhas += ["", f"Observação da nossa equipe: {d['comentario']}"]
    linhas += ["", "Pedimos que envie a nota corrigida ou a justificativa (por exemplo, o aditivo assinado) respondendo este e-mail.",
               "", "Atenciosamente,", f"{u['nome']}, equipe Bernhoeft, em nome de {d['cliente']}"]
    corpo = "\n".join(linhas)
    db.x("INSERT INTO avisos(ws, divergencia_id, nota_id, fornecedor_id, para, assunto, corpo, usuario, quando) VALUES(?,?,?,?,?,?,?,?,?)",
         (d["ws"], did, d["nota_id"], d["fornecedor_id"], d["email"], assunto, corpo, u["nome"], db.agora()))
    db.trilha(d["ws"], u["nome"], f"gerou aviso ao fornecedor {nome} sobre a nota {d['numero']} ({titulo})")
    return {"para": d["email"], "assunto": assunto, "corpo": corpo, "responsavel": d["responsavel"],
            "msg": "Aviso pronto. Copie ou abra no seu e-mail para enviar." if d["email"]
            else "Aviso pronto, mas o fornecedor não tem e-mail cadastrado. Cadastre em Fornecedores."}


@app.get("/api/ws/{ws}/notas")
def notas(ws: str):
    _ws(ws)
    L = db.q("""SELECT n.*, c.numero contrato_numero,
               (SELECT COUNT(*) FROM divergencias d WHERE d.nota_id=n.id AND d.status='aberta') abertas
               FROM notas n LEFT JOIN contratos c ON c.id=n.contrato_id WHERE n.ws=?
               ORDER BY n.data_emissao DESC, n.id DESC""", (ws,))
    return [_nota_publica(n) for n in L]


@app.get("/api/notas/{nid}")
def nota(nid: int):
    n = db.q("SELECT * FROM notas WHERE id=?", (nid,), um=True)
    if not n:
        raise HTTPException(404, "Nota não encontrada")
    out = _nota_publica(n)
    out["tem_xml"] = bool(n["xml"])
    out["contrato"] = db.q("SELECT * FROM contratos WHERE id=?", (n["contrato_id"],), um=True) if n["contrato_id"] else None
    out["aditivos"] = []
    if out["contrato"]:
        out["contrato"]["cnpj_fmt"] = fmt_cnpj(out["contrato"]["cnpj_prestador"])
        out["aditivos"] = conciliacao._aditivos_do_contrato(out["contrato"], db.q("SELECT * FROM aditivos WHERE ws=?", (n["ws"],)))
    out["divergencias"] = db.q("SELECT * FROM divergencias WHERE nota_id=? ORDER BY id", (nid,))
    for d in out["divergencias"]:
        d["titulo"] = conciliacao.REGRAS[d["regra"]][0]
    return out


@app.get("/api/notas/{nid}/xml")
def nota_xml(nid: int):
    n = db.q("SELECT numero, xml FROM notas WHERE id=?", (nid,), um=True)
    if not n or not n["xml"]:
        raise HTTPException(404, "Esta nota não veio por XML")
    return Response(n["xml"], media_type="application/xml",
                    headers={"Content-Disposition": _anexo(f"NFSe-{n['numero']}.xml")})


@app.get("/api/ws/{ws}/contratos")
def contratos(ws: str):
    _ws(ws)
    aditivos = db.q("SELECT * FROM aditivos WHERE ws=?", (ws,))
    L = db.q("""SELECT c.*, (SELECT COUNT(*) FROM notas n WHERE n.contrato_id=c.id) notas,
               (SELECT COALESCE(SUM(valor),0) FROM notas n WHERE n.contrato_id=c.id) faturado,
               (SELECT COUNT(*) FROM divergencias d WHERE d.contrato_id=c.id AND d.status='aberta') abertas
               FROM contratos c WHERE c.ws=? ORDER BY c.nome_prestador, c.numero""", (ws,))
    for c in L:
        c["cnpj_fmt"] = fmt_cnpj(c["cnpj_prestador"])
        c["aditivos"] = conciliacao._aditivos_do_contrato(c, aditivos)
    soltos = [a for a in aditivos if not any(a in c["aditivos"] for c in L)]
    return {"contratos": L, "aditivos_sem_contrato": soltos}


@app.get("/api/ws/{ws}/fornecedores")
def fornecedores(ws: str):
    _ws(ws)
    L = db.q("""SELECT f.*, (SELECT COUNT(*) FROM contratos c WHERE c.fornecedor_id=f.id) contratos,
               (SELECT COUNT(*) FROM notas n WHERE n.fornecedor_id=f.id) notas,
               (SELECT COALESCE(SUM(valor),0) FROM notas n WHERE n.fornecedor_id=f.id) faturado,
               (SELECT COUNT(*) FROM divergencias d WHERE d.fornecedor_id=f.id AND d.status='aberta') abertas,
               (SELECT COUNT(*) FROM divergencias d WHERE d.fornecedor_id=f.id AND d.status='rejeitada') rejeitadas,
               (SELECT MAX(data_emissao) FROM notas n WHERE n.fornecedor_id=f.id) ultima
               FROM fornecedores f WHERE f.ws=? ORDER BY abertas DESC, f.nome""", (ws,))
    # Contrato que ainda está em "Dúvidas da leitura": não é "sem contrato", é "aguardando confirmação".
    em_duvida = {}
    for d in db.q("SELECT id FROM docs WHERE ws=? AND status='revisao' AND tipo=? AND dados IS NULL", (ws, fiscal.TIPO_CONTRATO)):
        conciliacao.extrair_doc(d["id"])  # envios antigos: lê os campos provisórios agora
    for d in db.q("SELECT id, dados FROM docs WHERE ws=? AND status='revisao' AND tipo=?", (ws, fiscal.TIPO_CONTRATO)):
        cnpj = (_j(d["dados"], {}) or {}).get("campos", {}).get("cnpj_prestador")
        if cnpj:
            em_duvida[cnpj] = d["id"]
    for f in L:
        f["cnpj_fmt"] = fmt_cnpj(f["cnpj"])
        f["contrato_em_duvida"] = em_duvida.get(f["cnpj"])
    return L


@app.post("/api/ws/{ws}/fornecedores")
def cadastrar_fornecedor(request: Request, ws: str, corpo: dict):
    """Cadastro manual (ou edição) de um fornecedor do cliente. O CNPJ é a chave."""
    _ws(ws)
    auth.exigir(request, "revisor")
    cnpj = fiscal.so_digitos(corpo.get("cnpj"))
    if not fiscal.cnpj_valido(cnpj):
        raise HTTPException(400, "CNPJ inválido. Confira os 14 números.")
    nome = (corpo.get("nome") or "").strip()
    if len(nome) < 2:
        raise HTTPException(400, "Informe a razão social do fornecedor.")
    campos = {k: (corpo.get(k) or "").strip() or None for k in ("email", "telefone", "responsavel")}
    atual = db.q("SELECT id FROM fornecedores WHERE ws=? AND cnpj=?", (ws, cnpj), um=True)
    if atual:
        db.x("UPDATE fornecedores SET nome=?, email=?, telefone=?, responsavel=? WHERE id=?",
             (nome, campos["email"], campos["telefone"], campos["responsavel"], atual["id"]))
        return {"ok": True, "msg": f"{nome} atualizado."}
    db.x("""INSERT INTO fornecedores(ws, cnpj, nome, email, telefone, responsavel, cadastro, criado_em)
            VALUES(?,?,?,?,?,?, 'manual', ?)""", (ws, cnpj, nome, campos["email"], campos["telefone"], campos["responsavel"], db.agora()))
    return {"ok": True, "msg": f"{nome} cadastrado. As notas e contratos com este CNPJ entram aqui."}


@app.post("/api/clientes")
def cadastrar_cliente(request: Request, corpo: dict):
    """Novo workspace (um cliente da empresa) dentro da conta de quem pediu."""
    u = auth.exigir(request, "admin")
    nome = (corpo.get("nome") or "").strip()
    if len(nome) < 2:
        raise HTTPException(400, "Informe o nome da empresa.")
    cnpj = fiscal.so_digitos(corpo.get("cnpj")) or None
    if cnpj and not fiscal.cnpj_valido(cnpj):
        raise HTTPException(400, "CNPJ inválido. Confira os 14 números ou deixe em branco.")
    if cnpj and db.q("SELECT 1 FROM workspaces WHERE cnpj=? AND conta_id=?", (cnpj, u["conta_id"])):
        raise HTTPException(400, "Já existe um workspace com esse CNPJ.")
    wid = seed.criar_cliente(nome, (corpo.get("setor") or "").strip(), cnpj, conta_id=u["conta_id"])
    return db.q("SELECT * FROM workspaces WHERE id=?", (wid,), um=True)


@app.post("/api/ws/{ws}/reconciliar")
def reconciliar(request: Request, ws: str):
    _ws(ws)
    auth.exigir(request, "revisor")
    return conciliacao.conciliar(ws)


# ------------------------------------------------------------------ documentos fiscais XML (55, 65 e 57)
@app.get("/api/ws/{ws}/documentos-fiscais")
def listar_documentos_fiscais(ws: str, modelo: str = ""):
    _ws(ws)
    if modelo and modelo not in ("55", "65", "57"):
        raise HTTPException(400, "Modelo fiscal não suportado")
    sql = """SELECT id, ws, envio_id, nome_arquivo, sha256, modelo, tipo,
             versao, numero, chave, emissao, emissor, destinatario, criado_em
             FROM documentos_fiscais WHERE ws=?"""
    args = [ws]
    if modelo:
        sql += " AND modelo=?"
        args.append(modelo)
    sql += " ORDER BY id DESC"
    return db.q(sql, tuple(args))


@app.get("/api/documentos-fiscais/{fid}")
def detalhar_documento_fiscal(fid: int):
    d = db.q("SELECT * FROM documentos_fiscais WHERE id=?", (fid,), um=True)
    if not d:
        raise HTTPException(404, "Documento fiscal não encontrado")
    dados = json.loads(d["dados"])
    dados["id"] = fid
    dados["envio_id"] = d["envio_id"]
    dados["nome_arquivo"] = d["nome_arquivo"]
    dados["criado_em"] = d["criado_em"]
    return dados


# ------------------------------------------------------------------ documentos
@app.get("/api/ws/{ws}/documentos")
def documentos(ws: str):
    cats = _cats(ws)
    limiar = int(db.get_config(ws)["limiar"])
    out = []
    for d in db.q("SELECT * FROM docs WHERE ws=? ORDER BY id DESC", (ws,)):
        doc = _doc_publico(d, cats, com_paginas=True)
        doc["limiar"] = limiar
        doc["total_paginas"] = len(doc["paginas"])
        out.append(doc)
    return out


@app.get("/api/docs/{did}")
def doc(did: int):
    d = _doc(did)
    cats = _cats(d["ws"])
    out = _doc_publico(d, cats, com_paginas=True)
    pags = db.q("SELECT texto FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n", (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    texto = "\n\n".join(p["texto"] or "" for p in pags)
    out["texto"] = anonimizar.mascarar_texto(texto, cats, _j(d["sensiveis"], []))
    out["protegidos"] = len(anonimizar.achar(texto, cats, _j(d["sensiveis"], [])))
    # Para explicar uma confiança baixa: quais páginas ficaram abaixo do limite e o que a IA observou nelas.
    out["limiar"] = int(db.get_config(d["ws"])["limiar"])
    out["fracas"] = [{"n": p["n"], "conf": p["conf"], "sinais": _j(p["sinais"], [])}
                     for p in db.q("SELECT n, conf, sinais FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? AND conf < ? ORDER BY conf",
                                   (d["envio_id"], d["pag_ini"], d["pag_fim"], out["limiar"]))][:4]
    return out


@app.delete("/api/docs/{did}")
def excluir_documento(request: Request, did: int):
    """Exclui o documento: some das telas, da busca e do ZIP; as imagens das páginas são apagadas do disco.
    As páginas ficam marcadas como 'excluida' para o documento não voltar se o envio for reagrupado."""
    from pathlib import Path
    u = auth.exigir(request, "revisor")
    d = _doc(did)
    pags = db.q("SELECT id, img FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ?", (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    for p in pags:
        caminhos = [p["img"]] if p["img"] else []
        caminhos += list((config.DADOS / "miniaturas").glob(f"{p['id']}_*.jpg"))
        armazenamento.apagar(caminhos)  # do disco e do Storage
    db.x("""UPDATE paginas SET status='excluida', img=NULL, texto=NULL, linhas=NULL, sensiveis=NULL, doc_id=NULL
            WHERE envio_id=? AND n BETWEEN ? AND ?""", (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    _limpar_extraidos(did)
    db.x("DELETE FROM busca WHERE doc_id=?", (did,))
    db.x("DELETE FROM docs WHERE id=?", (did,))
    db.trilha(d["ws"], u["nome"], f"excluiu o documento #{did} ({d['tipo']}, envio #{d['envio_id']}, páginas {d['pag_ini']}–{d['pag_fim']})")
    db.evento(d["envio_id"], f"{u['nome']} excluiu o documento {d['tipo']} (páginas {d['pag_ini']}–{d['pag_fim']}).")
    conciliacao.conciliar(d["ws"])
    return {"ok": True, "msg": f"{d['tipo']} excluído (páginas {d['pag_ini']}–{d['pag_fim']} do envio #{d['envio_id']})."}


@app.post("/api/docs/{did}/revelar")
def revelar(request: Request, did: int, corpo: dict):
    u = auth.exigir(request, "revisor")
    d = _doc(did)
    motivo = (corpo.get("motivo") or "").strip()
    if len(motivo) < 5:
        raise HTTPException(400, "Escreva o motivo para ver os dados protegidos.")
    db.x("INSERT INTO acessos(ws, doc_id, quando, motivo, usuario) VALUES(?,?,?,?,?)",
         (d["ws"], did, db.agora(), motivo, u["nome"]))
    pags = db.q("SELECT texto FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n", (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    return {"texto": "\n\n".join(p["texto"] or "" for p in pags), "cpf": d["cpf"]}


def _anexo(nome: str) -> str:
    """Content-Disposition que aceita acento e qualquer caractere vindo do XML ou do OCR
    (o cabeçalho só aceita latin-1: um nome como “Serviços Ltda” derrubava o download)."""
    simples = re.sub(r"[^A-Za-z0-9._-]+", "_", nome)
    return f"attachment; filename=\"{simples}\"; filename*=UTF-8''{quote(nome)}"


def _nome_arquivo(d) -> str:
    return re.sub(r"[^\w-]+", "-", f"{d['tipo']}-{d['empresa'] or 'doc'}-{d['id']}").strip("-")


@app.get("/api/ws/{ws}/documentos.zip")
def baixar_tudo(ws: str):
    """Todos os documentos prontos, em PDF pesquisável, numa pasta por tipo (o "retorno" do sistema)."""
    import zipfile
    w = _ws(ws)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for d in db.q("SELECT * FROM docs WHERE ws=? AND status='confirmado' ORDER BY tipo, id", (ws,)):
            pasta = re.sub(r"[^\w ()-]+", "", d["tipo"]).strip() or "Outros"
            z.writestr(f"{pasta}/{_nome_arquivo(d)}.pdf", _pdf_doc(d))
    return Response(buf.getvalue(), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="concilia-{w["id"]}-documentos.zip"'})


@app.get("/api/docs/{did}/pdf")
def pdf_pesquisavel(did: int):
    d = _doc(did)
    return Response(_pdf_doc(d), media_type="application/pdf",
                    headers={"Content-Disposition": _anexo(f"{_nome_arquivo(d)}.pdf")})


def _pdf_doc(d) -> bytes:
    """PDF do documento: a imagem de cada página com o texto do OCR por baixo (pesquisável), dados protegidos escondidos."""
    cats = _cats(d["ws"])
    pags = db.q("SELECT * FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n", (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    sens = _j(d["sensiveis"], [])
    saida = fitz.open()
    for p in pags:
        img = armazenamento.local(p["img"])
        if not img:
            continue  # imagem perdida: o PDF sai com as páginas que existem
        im = anonimizar.mascarar_imagem(img, _j(p["linhas"], []), cats, sens)
        s = 0.5
        largura, altura = im.width, im.height
        # JPEG em até 1400 px: o PDF fica ~50x menor que PNG em resolução cheia e o texto continua legível.
        foto = im.convert("RGB")
        if max(foto.size) > 1400:
            foto.thumbnail((1400, 1400))
        buf = io.BytesIO()
        foto.save(buf, "JPEG", quality=72, optimize=True)
        pg = saida.new_page(width=largura * s, height=altura * s)
        pg.insert_image(pg.rect, stream=buf.getvalue())
        for ln in _j(p["linhas"], []):
            t = anonimizar.mascarar_texto(ln.get("text", ""), cats, sens)
            x0, y0, x1, y1 = ln["box"]
            tam = max(4, (y1 - y0) * s * 0.75)
            try:
                pg.insert_text((x0 * s, y1 * s - 1), t, fontsize=tam, render_mode=3)
            except Exception:
                pass
    return saida.tobytes()


# ------------------------------------------------------------------ busca
@app.get("/api/ws/{ws}/busca")
def busca(ws: str, q: str = ""):
    termos = re.findall(r"\w+", analise.norm(q))
    if not termos:
        return []
    cats = _cats(ws)
    try:
        # Trecho sem marcadores: a máscara roda no texto limpo (marcadores no meio de um CPF ou e-mail
        # impediam o reconhecimento) e o destaque é aplicado só depois, no texto já mascarado.
        linhas = db.buscar_texto(ws, termos)
    except Exception:
        return []
    out = []
    for r in linhas:
        d = db.q("SELECT * FROM docs WHERE id=?", (r["doc_id"],), um=True)
        if not d:
            continue
        item = _doc_publico(d, cats)
        item["trecho"] = _destacar(anonimizar.mascarar_texto(r["trecho"], cats, _j(d["sensiveis"], [])), termos)
        out.append(item)
    return out


def _destacar(texto: str, termos: list[str]) -> str:
    """Marca com [[ ]] as palavras que começam por um dos termos buscados (a tela troca por <mark>)."""
    def marcar(m):
        palavra = m.group(0)
        return f"[[{palavra}]]" if any(analise.norm(palavra).startswith(t) for t in termos) else palavra
    return re.sub(r"\w+", marcar, texto)


# ------------------------------------------------------------------ relatórios
class _CsvSeguro:
    """Escreve o CSV neutralizando fórmulas: texto vindo de nota ou contrato que comece com = + - @ seria
    executado pelo Excel ao abrir a planilha (ex.: =HYPERLINK(...))."""
    def __init__(self, wr):
        self.wr = wr

    def writerow(self, linha):
        self.wr.writerow(["'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v for v in linha])


@app.get("/api/ws/{ws}/relatorios")
def relatorios(ws: str, mes: str = ""):
    """Números da tela Relatórios: notas conferidas no mês (pela data de emissão) e divergências por regra."""
    _ws(ws)
    contagem = {r["m"]: r["c"] for r in db.q("""SELECT substr(data_emissao,1,7) m, COUNT(*) c FROM notas
                                                 WHERE ws=? AND data_emissao IS NOT NULL GROUP BY m""", (ws,)) if r["m"]}
    meses = sorted(contagem, reverse=True)
    if mes not in meses:
        # Sem mês escolhido: o mês com mais notas (uma nota solta com data errada não vira o mês da tela).
        mes = max(meses, key=lambda m: (contagem[m], m)) if meses else ""
    por_status = {r["status"]: r["c"] for r in db.q(
        "SELECT status, COUNT(*) c FROM notas WHERE ws=? AND substr(data_emissao,1,7)=? GROUP BY status", (ws, mes))}
    por_regra = {r["regra"]: r["c"] for r in db.q(
        """SELECT d.regra, COUNT(*) c FROM divergencias d JOIN notas n ON n.id=d.nota_id
           WHERE d.ws=? AND substr(n.data_emissao,1,7)=? GROUP BY d.regra""", (ws, mes))}
    return {"meses": meses, "mes": mes,
            "notas": {"total": sum(por_status.values()),
                      "sem_divergencia": por_status.get("conciliada", 0) + por_status.get("aprovada", 0),
                      "com_divergencia": por_status.get("divergente", 0) + por_status.get("rejeitada", 0),
                      "aguardando_contrato": por_status.get("pendente", 0)},
            "regras": [{"regra": k, "titulo": t, "severidade": s, "total": por_regra.get(k, 0)}
                       for k, (t, s) in conciliacao.REGRAS.items()]}


@app.get("/api/ws/{ws}/relatorio.csv")
def relatorio(ws: str, tipo: str = "divergencias"):
    w = _ws(ws)
    buf = io.StringIO()
    wr = _CsvSeguro(csv.writer(buf, delimiter=";"))
    if tipo == "divergencias":
        wr.writerow(["Nota", "Prestador", "CNPJ", "Emissão", "Valor da nota", "Contrato", "Regra", "Gravidade",
                     "O que aconteceu", "Esperado", "Encontrado", "Situação", "Decidido por", "Quando", "Comentário"])
        for d in divergencias(ws, "todas")["divergencias"]:
            wr.writerow([d["numero"], d["nome_prestador"] or "", d["cnpj_fmt"], fmt_data(d["data_emissao"]), brl(d["valor"]),
                         d["contrato_numero"] or "", d["titulo"], d["severidade"], d["mensagem"], d["esperado"] or "",
                         d["encontrado"] or "", d["status"], d["decidido_por"] or "", d["decidido_em"] or "", d["comentario"] or ""])
    elif tipo == "notas":
        wr.writerow(["Número", "Prestador", "CNPJ", "Emissão", "Competência", "Serviço", "Valor", "Contrato",
                     "Situação", "Divergências abertas", "Origem", "Observação"])
        for n in notas(ws):
            wr.writerow([n["numero"], n["nome_prestador"] or "", n["cnpj_fmt"], fmt_data(n["data_emissao"]), n["competencia"] or "",
                         n["descricao"] or "", brl(n["valor"]), n["contrato_numero"] or "", n["status"], n["abertas"],
                         "XML" if n["origem"] == "xml" else "PDF", n["observacao"] or ""])
    elif tipo == "fornecedores":
        wr.writerow(["Fornecedor", "CNPJ", "Contratos", "Notas", "Total faturado", "Divergências abertas", "Rejeitadas", "Última nota"])
        for f in fornecedores(ws):
            wr.writerow([f["nome"] or "", f["cnpj_fmt"], f["contratos"], f["notas"], brl(f["faturado"]), f["abertas"],
                         f["rejeitadas"], fmt_data(f["ultima"])])
    elif tipo == "avisos":
        wr.writerow(["Quando", "Quem gerou", "Para", "Assunto", "Mensagem"])
        for a in db.q("SELECT * FROM avisos WHERE ws=? ORDER BY id", (ws,)):
            wr.writerow([a["quando"], a["usuario"], a["para"] or "(sem e-mail)", a["assunto"], a["corpo"]])
    elif tipo == "trilha":
        wr.writerow(["Quando", "Quem", "O que fez"])
        for t in db.q("SELECT * FROM trilha WHERE ws=? ORDER BY id", (ws,)):
            wr.writerow([t["quando"], t["usuario"], t["texto"]])
    elif tipo == "acessos":
        wr.writerow(["Quando", "Quem", "Documento", "Motivo"])
        for a in db.q("SELECT * FROM acessos WHERE ws=? ORDER BY id", (ws,)):
            wr.writerow([a["quando"], a.get("usuario") or "", a["doc_id"], a["motivo"]])
    else:
        wr.writerow(["Documento", "Envio", "Tipo", "Empresa", "Páginas", "Confiança", "Situação", "Decisão humana"])
        for d in db.q("SELECT * FROM docs WHERE ws=? ORDER BY id", (ws,)):
            wr.writerow([d["id"], d["envio_id"], d["tipo"], d["empresa"] or "",
                         f"{d['pag_ini']}-{d['pag_fim']}", d["conf"], d["status"], d["decisao"] or ""])
    nome = f"concilia-{w['id']}-{tipo}.csv"
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nome}"'})


# ------------------------------------------------------------------ configurações
@app.get("/api/ws/{ws}/config")
def ler_config(ws: str):
    _ws(ws)
    return {"config": db.get_config(ws), "tipos": db.tipos_ws(ws),
            "claude_configurado": config.claude_configurado(), "modelo": config.MODELO,
            "acessos": db.q("SELECT COUNT(*) c FROM acessos WHERE ws=?", (ws,), um=True)["c"]}


@app.post("/api/ws/{ws}/config")
def salvar_config(request: Request, ws: str, corpo: dict):
    _ws(ws)
    auth.exigir(request, "admin")
    for k, v in corpo.items():
        if k in ("cpf", "banco", "saude", "endereco", "contato", "usar_claude"):
            db.set_config(ws, k, "1" if v in (True, 1, "1") else "0")
        elif k in ("limiar", "tolerancia"):
            try:
                n = float(str(v).replace(",", "."))
            except (TypeError, ValueError):
                raise HTTPException(400, f"Valor inválido para {k}: use um número.") from None
            if k == "limiar":
                db.set_config(ws, k, max(40, min(99, int(n))))
            else:
                db.set_config(ws, k, max(0.0, min(20.0, n)))
    if "tolerancia" in corpo:
        conciliacao.conciliar(ws)
    return db.get_config(ws)


@app.post("/api/ws/{ws}/tipos")
def novo_tipo(request: Request, ws: str, corpo: dict):
    _ws(ws)
    auth.exigir(request, "admin")
    nome = (corpo.get("nome") or "").strip()
    if len(nome) < 2:
        raise HTTPException(400, "Dê um nome ao tipo de documento.")
    if db.q("SELECT 1 FROM tipos WHERE ws=? AND lower(nome)=lower(?)", (ws, nome)):
        raise HTTPException(400, "Esse tipo já existe neste cliente.")
    titulos = [analise.norm(t.strip()) for t in (corpo.get("titulos") or "").split(",") if t.strip()]
    palavras = [analise.norm(t.strip()) for t in (corpo.get("palavras") or "").split(",") if t.strip()]
    if not titulos and not palavras:
        raise HTTPException(400, "Informe pelo menos um título ou palavra típica do documento.")
    db.x("INSERT INTO tipos(ws, nome, titulos, palavras, exigido) VALUES(?,?,?,?,?)",
         (ws, nome, json.dumps(titulos), json.dumps(palavras), 0))
    return {"ok": True}


# Arquivos do front novo (scripts, estilos, imagens). Fica por último: as rotas /api têm prioridade.
if (FRONT_PRONTO / "index.html").exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=FRONT_PRONTO), name="front")
