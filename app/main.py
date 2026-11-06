"""Servidor da Concilia AI: API + telas. Rode com:  uvicorn app.main:app --port 8000"""
import csv
import io
import json
import re
from contextlib import asynccontextmanager

import pymupdf as fitz
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from . import analise, anonimizar, auth, avaliacao, config, db, pipeline, seed

trabalhador = pipeline.Trabalhador()
MAX_BYTES = 40 * 1024 * 1024  # por arquivo, como na versão Docker
PUBLICAS = {"/api/login", "/api/estado", "/api/sair"}


@asynccontextmanager
async def vida(app):
    seed.semear()
    auth.criar_usuarios_padrao()
    if not trabalhador.is_alive():
        trabalhador.start()
    yield


app = FastAPI(title="Concilia AI", lifespan=vida)


@app.middleware("http")
async def exigir_login(request: Request, chamar):
    if request.url.path.startswith("/api/") and request.url.path not in PUBLICAS:
        u = auth.usuario_da_requisicao(request)
        if not u:
            return JSONResponse({"detail": "Entre na sua conta para continuar."}, status_code=401)
        request.state.usuario = u
    return await chamar(request)


@app.post("/api/login")
def login(corpo: dict):
    token, u = auth.entrar(corpo.get("usuario"), corpo.get("senha"))
    r = JSONResponse(u)
    r.set_cookie(auth.COOKIE, token, max_age=auth.DURACAO, httponly=True, samesite="lax")
    return r


@app.post("/api/sair")
def sair():
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
    if com_paginas:
        out["paginas"] = db.q("SELECT id, n, tipo, conf, inicio FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n",
                              (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    return out


# ------------------------------------------------------------------ telas
@app.get("/")
def tela():
    return FileResponse(config.WEB / "index.html")


@app.get("/api/estado")
def estado(request: Request):
    u = auth.usuario_da_requisicao(request)
    return {
        "claude_configurado": config.claude_configurado(),
        "modelo": config.MODELO,
        "usuario": {k: u[k] for k in ("usuario", "nome", "perfil")} if u else None,
        "clientes": db.q("SELECT * FROM workspaces ORDER BY ordem") if u else [],
    }


# ------------------------------------------------------------------ início
@app.get("/api/ws/{ws}/resumo")
def resumo(ws: str):
    _ws(ws)
    pags = db.q("SELECT COALESCE(SUM(feitas),0) s FROM envios WHERE ws=?", (ws,), um=True)["s"]
    total = db.q("SELECT COUNT(*) c FROM docs WHERE ws=?", (ws,), um=True)["c"]
    auto = db.q("SELECT COUNT(*) c FROM docs WHERE ws=? AND decisao IS NULL AND status='confirmado'", (ws,), um=True)["c"]
    pend = db.q("SELECT COUNT(*) c FROM docs WHERE ws=? AND status='revisao'", (ws,), um=True)["c"]
    ativo = db.q("SELECT * FROM envios WHERE ws=? AND status IN ('fila','processando','pausado','falhou') ORDER BY id DESC LIMIT 1", (ws,), um=True)
    ultimo = db.q("SELECT * FROM envios WHERE ws=? AND status='concluido' ORDER BY id DESC LIMIT 1", (ws,), um=True)
    prontos = db.q("SELECT COUNT(*) c FROM docs WHERE envio_id=? AND status='confirmado'", (ultimo["id"],), um=True)["c"] if ultimo else 0
    m = matriz(ws)
    alertas = []
    for g in m["grupos"]:
        for linha in g["linhas"]:
            for c in linha["celulas"]:
                if c["status"] == "falta":
                    alertas.append({"tipo": "falta", "texto": f"{linha['pessoa']} está sem {c['tipo']}", "sub": g["empresa"]})
    for d in db.q("SELECT * FROM docs WHERE ws=? AND status='revisao' ORDER BY id LIMIT 3", (ws,)):
        alertas.append({"tipo": "revisao", "texto": f"{d['tipo']} de {d['pessoa'] or 'pessoa não identificada'} espera sua confirmação",
                        "sub": f"Envio #{d['envio_id']} · páginas {d['pag_ini']}–{d['pag_fim']}"})
    return {"paginas": pags, "documentos": total, "automaticos": auto, "pendencias": pend,
            "pct_auto": round(100 * auto / total) if total else None, "horas": round(total * 2.5 / 60, 1),
            "ativo": ativo, "ultimo": ultimo, "prontos": prontos, "alertas": alertas[:6],
            "envios": db.q("SELECT * FROM envios WHERE ws=? ORDER BY id DESC LIMIT 5", (ws,))}


# ------------------------------------------------------------------ envios
@app.post("/api/ws/{ws}/envios")
async def enviar(request: Request, ws: str, arquivos: list[UploadFile] = File(...), origem: str = Form("")):
    _ws(ws)
    u = auth.exigir(request, "operador")
    dados = []
    for a in arquivos:
        conteudo = await a.read(MAX_BYTES + 1)
        if len(conteudo) > MAX_BYTES:
            raise HTTPException(413, f"“{a.filename}” passa de 40 MB. Divida o arquivo e envie de novo.")
        dados.append((a.filename or "arquivo", conteudo))
    eid = pipeline.criar_envio(ws, dados, origem or f"Enviado por {u['nome']}", usuario=u["usuario"])
    trabalhador.acordar.set()
    return db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)


@app.post("/api/ws/{ws}/exemplo")
def enviar_exemplo(request: Request, ws: str):
    """Envia um lote de exemplo (para demonstração)."""
    _ws(ws)
    u = auth.exigir(request, "operador")
    if ws == "atlantica":
        pasta = avaliacao.gerar_lote(fornecedores=4, notas=3)
        lote = pasta / "lotes" / "lote_misturado.pdf"
        eid = pipeline.criar_envio(ws, [(lote.name, lote.read_bytes())], "Lote sintético com gabarito",
                                   usuario=u["usuario"], permitir_repetido=True)
        db.x("UPDATE envios SET gabarito=? WHERE id=?", (str(pasta / "ground_truth.json"), eid))
        trabalhador.acordar.set()
        return db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)
    pasta = config.BASE / "exemplos"
    nomes = ["lote-construtora.pdf"] if ws == "valealto" else ["lote-misturado-horizonte.pdf", "foto-aso-celular.jpg"]
    arquivos = [(n, (pasta / n).read_bytes()) for n in nomes if (pasta / n).exists()]
    if not arquivos:
        raise HTTPException(404, "Lote de exemplo não encontrado. Rode ferramentas\\gerar_exemplo.py.")
    eid = pipeline.criar_envio(ws, arquivos, "Lote de exemplo", usuario=u["usuario"], permitir_repetido=True)
    trabalhador.acordar.set()
    return db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)


@app.post("/api/ws/{ws}/avaliacao")
def nova_avaliacao(request: Request, ws: str, corpo: dict | None = None):
    """Gera um lote sintético com gabarito e envia para medir o acerto da IA."""
    _ws(ws)
    u = auth.exigir(request, "admin")
    corpo = corpo or {}
    fornecedores = max(3, min(20, int(corpo.get("fornecedores", 4))))
    pasta = avaliacao.gerar_lote(fornecedores=fornecedores, notas=3, digitalizar=bool(corpo.get("digitalizar", True)))
    lote = pasta / "lotes" / "lote_misturado.pdf"
    eid = pipeline.criar_envio(ws, [(lote.name, lote.read_bytes())], "Avaliação com gabarito",
                               usuario=u["usuario"], permitir_repetido=True)
    db.x("UPDATE envios SET gabarito=? WHERE id=?", (str(pasta / "ground_truth.json"), eid))
    trabalhador.acordar.set()
    return db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)


@app.get("/api/ws/{ws}/avaliacoes")
def avaliacoes(ws: str):
    out = []
    for e in db.q("SELECT * FROM envios WHERE ws=? AND gabarito IS NOT NULL ORDER BY id DESC", (ws,)):
        out.append({"envio": e, "resultado": avaliacao.medir_envio(e["id"])})
    return out


@app.get("/api/ws/{ws}/envios")
def envios(ws: str):
    return db.q("SELECT * FROM envios WHERE ws=? ORDER BY id DESC", (ws,))


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
    return {"envio": e, "paginas": pags, "docs": docs,
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


@app.post("/api/envios/{eid}/simular-falha")
def simular_falha(request: Request, eid: int):
    auth.exigir(request, "operador")
    db.x("UPDATE envios SET falha_simulada=1 WHERE id=?", (eid,))
    return {"ok": True}


# ------------------------------------------------------------------ páginas
@app.get("/api/paginas/{pid}/imagem")
def imagem(pid: int, largura: int = 0, revelar: int = 0):
    p = db.q("SELECT p.*, e.ws FROM paginas p JOIN envios e ON e.id=p.envio_id WHERE p.id=?", (pid,), um=True)
    if not p or not p["img"]:
        raise HTTPException(404, "Página ainda não processada")
    cats = [] if revelar else _cats(p["ws"])
    im = anonimizar.mascarar_imagem(p["img"], _j(p["linhas"], []), cats, _j(p["sensiveis"], []))
    if largura:
        im.thumbnail((largura, largura * 2))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})


# ------------------------------------------------------------------ pendências
@app.get("/api/ws/{ws}/pendencias")
def pendencias(ws: str):
    cats = _cats(ws)
    out = []
    for d in db.q("SELECT * FROM docs WHERE ws=? AND status='revisao' ORDER BY id", (ws,)):
        doc = _doc_publico(d, cats, com_paginas=True)
        # Mostra uma página antes e uma depois para decidir fronteiras.
        doc["vizinhas"] = db.q("SELECT id, n, tipo, doc_id FROM paginas WHERE envio_id=? AND n IN (?,?) ORDER BY n",
                               (d["envio_id"], d["pag_ini"] - 1, d["pag_fim"] + 1))
        out.append(doc)
    tipos = [t["nome"] for t in db.tipos_ws(ws)]
    return {"pendencias": out, "tipos": tipos, "limiar": int(db.get_config(ws)["limiar"])}


@app.post("/api/docs/{did}/decisao")
def decisao(request: Request, did: int, corpo: dict):
    u = auth.exigir(request, "revisor")
    resultado = _decidir(did, corpo)
    db.x("UPDATE docs SET decidido_por=? WHERE id=?", (u["nome"], did))
    return resultado


def _decidir(did: int, corpo: dict):
    d = _doc(did)
    acao = corpo.get("acao")
    agora = db.agora()
    if acao == "confirmar":
        tipo = corpo.get("tipo") or d["tipo"]
        db.x("UPDATE docs SET tipo=?, status='confirmado', decisao=?, decidido_em=? WHERE id=?",
             (tipo, f"Confirmado como {tipo}", agora, did))
        pipeline.aprender(d["ws"], tipo, did)
        return {"ok": True, "msg": f"Confirmado como {tipo}."}
    if acao == "dividir":
        n = int(corpo.get("pagina", 0))
        if not (d["pag_ini"] < n <= d["pag_fim"]):
            raise HTTPException(400, "Escolha uma página do meio do documento para começar o novo.")
        p = db.q("SELECT * FROM paginas WHERE envio_id=? AND n=?", (d["envio_id"], n), um=True)
        db.x("UPDATE paginas SET inicio=1 WHERE id=?", (p["id"],))
        db.x("UPDATE docs SET pag_fim=?, status='confirmado', decisao=?, decidido_em=? WHERE id=?",
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
        db.x("UPDATE docs SET pag_fim=?, status='confirmado', decisao=?, decidido_em=? WHERE id=?",
             (d["pag_fim"], f"Juntado com as páginas {d['pag_ini']}–{d['pag_fim']}", agora, ant["id"]))
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
            r = analise.analisar(p["img"], p["texto"], tipos, anterior, ex, cfg.get("usar_claude") == "1")
            db.x("UPDATE paginas SET tipo=?, conf=?, sinais=?, candidatos=?, motor=? WHERE id=?",
                 (r["tipo"], r["conf"], json.dumps(r["sinais"], ensure_ascii=False),
                  json.dumps(r["candidatos"], ensure_ascii=False), r["motor"], p["id"]))
            confs.append(r["conf"])
            primeira = primeira or r
        conf = min(confs)
        status = "revisao" if conf < int(cfg["limiar"]) else "confirmado"
        db.x("UPDATE docs SET tipo=?, conf=?, status=?, sinais=?, candidatos=?, decisao=? WHERE id=?",
             (primeira["tipo"], conf, status, json.dumps(primeira["sinais"], ensure_ascii=False),
              json.dumps(primeira["candidatos"], ensure_ascii=False), "Reprocessado", did))
        msg = "Reprocessado. Continua precisando de você." if status == "revisao" else f"Reprocessado: {primeira['tipo']}, confiança {conf}%."
        return {"ok": True, "msg": msg}
    raise HTTPException(400, "Ação desconhecida")


# ------------------------------------------------------------------ documentos
def _e_pessoa(nome):
    return bool(nome) and not analise.RE_EMPRESA_NOME.search(nome)


@app.get("/api/ws/{ws}/matriz")
def matriz(ws: str):
    exigidos = [t["nome"] for t in db.tipos_ws(ws) if t["exigido"]]
    docs = db.q("SELECT * FROM docs WHERE ws=? AND status != 'aguardando' ORDER BY id", (ws,))
    # Grafias da mesma empresa (texto do PDF x OCR) viram uma só; mostra a grafia com acento, se houver.
    grafias = {}
    for d in docs:
        if d["empresa"]:
            k = analise.chave_nome(d["empresa"])
            atual = grafias.get(k)
            if not atual or (analise.norm(atual) == atual.lower() and analise.norm(d["empresa"]) != d["empresa"].lower()):
                grafias[k] = d["empresa"]
    pessoas = {}
    # Primeiro cria as linhas a partir dos documentos exigidos por pessoa; depois encaixa os outros.
    ordenados = [d for d in docs if d["tipo"] in exigidos] + [d for d in docs if d["tipo"] not in exigidos]
    for d in ordenados:
        if not _e_pessoa(d["pessoa"]):
            continue
        k = analise.chave_nome(d["pessoa"])
        if k not in pessoas and d["tipo"] not in exigidos:
            continue
        info = pessoas.setdefault(k, {"pessoa": d["pessoa"], "empresa": None, "docs": {}})
        if d["empresa"] and not info["empresa"]:
            info["empresa"] = grafias.get(analise.chave_nome(d["empresa"]), d["empresa"])
        atual = info["docs"].get(d["tipo"])
        if not atual or (atual["status"] != "confirmado" and d["status"] == "confirmado"):
            info["docs"][d["tipo"]] = d
    grupos = {}
    for info in pessoas.values():
        celulas = []
        for t in exigidos:
            d = info["docs"].get(t)
            st = "falta" if not d else ("ok" if d["status"] == "confirmado" else "rev")
            celulas.append({"tipo": t, "status": st, "doc_id": d["id"] if d else None})
        grupos.setdefault(info["empresa"] or "Empresa não identificada", []).append(
            {"pessoa": info["pessoa"], "celulas": celulas})
    empresa_docs = [_doc_publico(d, _cats(ws)) for d in docs if not _e_pessoa(d["pessoa"])]
    return {"exigidos": exigidos,
            "grupos": [{"empresa": k, "linhas": sorted(v, key=lambda l: l["pessoa"])} for k, v in sorted(grupos.items())],
            "sem_pessoa": empresa_docs}


@app.get("/api/ws/{ws}/documentos")
def documentos(ws: str):
    cats = _cats(ws)
    return [_doc_publico(d, cats) for d in db.q("SELECT * FROM docs WHERE ws=? ORDER BY id DESC", (ws,))]


@app.get("/api/docs/{did}")
def doc(did: int):
    d = _doc(did)
    cats = _cats(d["ws"])
    out = _doc_publico(d, cats, com_paginas=True)
    pags = db.q("SELECT texto FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n", (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    texto = "\n\n".join(p["texto"] or "" for p in pags)
    out["texto"] = anonimizar.mascarar_texto(texto, cats, _j(d["sensiveis"], []))
    out["protegidos"] = len(anonimizar.achar(texto, cats, _j(d["sensiveis"], [])))
    return out


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


@app.get("/api/docs/{did}/pdf")
def pdf_pesquisavel(did: int):
    d = _doc(did)
    cats = _cats(d["ws"])
    pags = db.q("SELECT * FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n", (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    sens = _j(d["sensiveis"], [])
    saida = fitz.open()
    for p in pags:
        im = anonimizar.mascarar_imagem(p["img"], _j(p["linhas"], []), cats, sens)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        s = 0.5
        pg = saida.new_page(width=im.width * s, height=im.height * s)
        pg.insert_image(pg.rect, stream=buf.getvalue())
        for ln in _j(p["linhas"], []):
            t = anonimizar.mascarar_texto(ln.get("text", ""), cats, sens)
            x0, y0, x1, y1 = ln["box"]
            tam = max(4, (y1 - y0) * s * 0.75)
            try:
                pg.insert_text((x0 * s, y1 * s - 1), t, fontsize=tam, render_mode=3)
            except Exception:
                pass
    dados = saida.tobytes()
    nome = re.sub(r"[^\w-]+", "-", f"{d['tipo']}-{d['pessoa'] or 'doc'}-{did}").strip("-")
    return Response(dados, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{nome}.pdf"'})


# ------------------------------------------------------------------ busca
@app.get("/api/ws/{ws}/busca")
def busca(ws: str, q: str = ""):
    termos = re.findall(r"\w+", analise.norm(q))
    if not termos:
        return []
    consulta = " AND ".join(f'"{t}"*' for t in termos)
    cats = _cats(ws)
    try:
        linhas = db.q("""SELECT doc_id, snippet(busca, 2, '[[', ']]', ' … ', 24) trecho FROM busca
                         WHERE busca MATCH ? AND ws=? ORDER BY rank LIMIT 30""", (consulta, ws))
    except Exception:
        return []
    out = []
    for r in linhas:
        d = db.q("SELECT * FROM docs WHERE id=?", (r["doc_id"],), um=True)
        if not d:
            continue
        item = _doc_publico(d, cats)
        item["trecho"] = anonimizar.mascarar_texto(r["trecho"], cats, _j(d["sensiveis"], []))
        out.append(item)
    return out


# ------------------------------------------------------------------ relatórios
@app.get("/api/ws/{ws}/relatorio.csv")
def relatorio(ws: str, tipo: str = "documentos"):
    w = _ws(ws)
    buf = io.StringIO()
    wr = csv.writer(buf, delimiter=";")
    if tipo == "situacao":
        m = matriz(ws)
        wr.writerow(["Empresa", "Colaborador"] + m["exigidos"])
        nomes = {"ok": "Ok", "rev": "Confirmar", "falta": "Falta"}
        for g in m["grupos"]:
            for l in g["linhas"]:
                wr.writerow([g["empresa"], l["pessoa"]] + [nomes[c["status"]] for c in l["celulas"]])
    elif tipo == "acessos":
        wr.writerow(["Quando", "Quem", "Documento", "Motivo"])
        for a in db.q("SELECT * FROM acessos WHERE ws=? ORDER BY id", (ws,)):
            wr.writerow([a["quando"], a.get("usuario") or "", a["doc_id"], a["motivo"]])
    else:
        wr.writerow(["Documento", "Envio", "Tipo", "Colaborador", "Empresa", "Páginas", "Confiança", "Situação", "Decisão humana"])
        for d in db.q("SELECT * FROM docs WHERE ws=? ORDER BY id", (ws,)):
            wr.writerow([d["id"], d["envio_id"], d["tipo"], d["pessoa"] or "", d["empresa"] or "",
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
        elif k == "limiar":
            db.set_config(ws, k, max(40, min(99, int(v))))
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
         (ws, nome, json.dumps(titulos), json.dumps(palavras), 1 if corpo.get("exigido") else 0))
    return {"ok": True}
