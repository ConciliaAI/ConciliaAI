"""Fila de envios: processa página por página, salva cada uma (ponto de retomada) e agrupa em documentos."""
import hashlib
import json
import threading
import time
import zipfile
from pathlib import Path

from . import analise, conciliacao, config, db, fiscal, ocr
from .classificacao_subtipos import identificar_subtipo, TIPO_COMPATIVEL
from .config import ENVIOS, PAGINAS

EXTS = (".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")


def importar_xml(eid: int, ws: str, caminho: Path, nome: str) -> bool:
    """Lê uma NFS-e em XML e grava a nota na hora (o XML não passa por OCR)."""
    conteudo = caminho.read_bytes()
    try:
        nota = fiscal.ler_nfse_xml(conteudo)
    except ValueError as erro:
        db.evento(eid, f"XML ignorado: {nome} ({erro})")
        return False
    _, nova = conciliacao.salvar_nota(ws, nota, "xml", eid, xml=conteudo.decode("utf-8", "replace"))
    if not nova:
        db.evento(eid, f"Nota {nota['numero']} ({nome}) já estava cadastrada: dados atualizados.")
    return True


# ------------------------------------------------------------------ envio novo
MAX_PAGINAS = config.MAX_PAGINAS  # por arquivo (CONCILIA_MAX_PAGINAS no .env)
MAX_BYTES = config.MAX_MB * 1024 * 1024  # por arquivo, também para cada arquivo de dentro de um ZIP
MAX_ZIP_TOTAL = 4 * MAX_BYTES  # soma do que sai de um ZIP (protege contra "zip bomb")


def _abrir_zip(caminho: Path, pasta: Path, i: int) -> list[Path]:
    """Extrai os arquivos aceitos de um ZIP, lendo com limite de tamanho (o tamanho declarado no ZIP pode mentir)."""
    saida, total = [], 0
    with zipfile.ZipFile(caminho) as z:
        for j, info in enumerate(sorted(z.infolist(), key=lambda k: k.filename)):
            if info.is_dir() or not info.filename.lower().endswith(EXTS + (".xml",)):
                continue
            with z.open(info) as f:
                conteudo = f.read(MAX_BYTES + 1)
            if len(conteudo) > MAX_BYTES:
                raise ValueError(f"“{Path(info.filename).name}” passa de {config.MAX_MB} MB descompactado")
            total += len(conteudo)
            if total > MAX_ZIP_TOTAL:
                raise ValueError(f"o conteúdo descompactado passa de {MAX_ZIP_TOTAL // (1024 * 1024)} MB")
            nome_z = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(info.filename).name)
            destino = pasta / f"{i:03d}_{j:03d}_{nome_z}"
            destino.write_bytes(conteudo)
            saida.append(destino)
    return saida


def criar_envio(ws: str, arquivos: list[tuple[str, bytes]], origem: str, usuario: str | None = None,
                permitir_repetido: bool = False) -> int:
    nome = arquivos[0][0] if len(arquivos) == 1 else f"{len(arquivos)} arquivos"
    eid = db.x("INSERT INTO envios(ws, nome, origem, criado_em, status, usuario) VALUES(?,?,?,?, 'recebendo', ?)",
               (ws, nome, origem, db.agora(), usuario))
    pasta = ENVIOS / str(eid)
    pasta.mkdir(parents=True, exist_ok=True)
    salvos, xmls = [], []
    for i, (nome_arq, conteudo) in enumerate(arquivos):
        digest = hashlib.sha256(conteudo).hexdigest()
        anterior = db.q("SELECT envio_id FROM arquivos WHERE ws=? AND sha256=?", (ws, digest), um=True)
        if anterior and not permitir_repetido:
            db.evento(eid, f"“{nome_arq}” já foi enviado no envio #{anterior['envio_id']}. Ignorado para não duplicar.")
            continue
        db.x("INSERT INTO arquivos(ws, sha256, envio_id, nome) VALUES(?,?,?,?)", (ws, digest, eid, nome_arq))
        seguro = f"{i:03d}_" + "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(nome_arq).name)
        caminho = pasta / seguro
        caminho.write_bytes(conteudo)
        if seguro.lower().endswith(".zip"):
            try:
                extraidos = _abrir_zip(caminho, pasta, i)
            except (zipfile.BadZipFile, ValueError, OSError) as erro:
                # Sem isso o envio ficava preso em "recebendo" e o mesmo arquivo não podia ser reenviado.
                db.x("DELETE FROM arquivos WHERE envio_id=? AND sha256=?", (eid, digest))
                db.evento(eid, f"ZIP ignorado: {nome_arq} ({erro if isinstance(erro, ValueError) else 'arquivo corrompido ou não é ZIP'})")
                continue
            for destino in extraidos:
                (xmls if destino.name.lower().endswith(".xml") else salvos).append(destino)
        elif seguro.lower().endswith(".xml"):
            xmls.append(caminho)
        elif seguro.lower().endswith(EXTS):
            salvos.append(caminho)
    n_xml = sum(importar_xml(eid, ws, x, x.name[4:]) for x in xmls)
    if n_xml:
        db.x("UPDATE envios SET notas_xml=? WHERE id=?", (n_xml, eid))
        db.evento(eid, f"{n_xml} nota(s) fiscal(is) lida(s) direto do XML, sem OCR.")
    n = 0
    for arq in salvos:
        try:
            paginas = ocr.contar_paginas(str(arq))
        except ValueError as erro:
            db.evento(eid, f"Arquivo ignorado: {arq.name[4:]} ({erro})")
            continue
        except Exception:
            db.evento(eid, f"Arquivo ignorado (não abriu): {arq.name[4:]}")
            continue
        if len(paginas) > MAX_PAGINAS:
            db.evento(eid, f"Arquivo ignorado: {arq.name[4:]} tem {len(paginas)} páginas (limite de {MAX_PAGINAS} por arquivo).")
            continue
        for idx, origem_t in paginas:
            n += 1
            db.x("INSERT INTO paginas(envio_id, n, arquivo, indice, origem_tipo) VALUES(?,?,?,?,?)",
                 (eid, n, str(arq), idx, origem_t))
    if n == 0 and n_xml:
        db.x("UPDATE envios SET status='concluido', terminado_em=? WHERE id=?", (db.agora(), eid))
        conciliacao.conciliar(ws)
    elif n == 0:
        ultimo = db.q("SELECT texto FROM eventos WHERE envio_id=? ORDER BY id DESC LIMIT 1", (eid,), um=True)
        db.x("UPDATE envios SET status='recusado', erro=? WHERE id=?",
             (ultimo["texto"] if ultimo else "Nenhum arquivo legível (use XML da NFS-e, PDF, imagem ou ZIP).", eid))
    else:
        db.x("UPDATE envios SET status='fila', total=? WHERE id=?", (n, eid))
        db.evento(eid, f"Recebido: {n} páginas em {len(salvos)} arquivo(s)")
        if n_xml:
            # Os contratos deste envio ainda vão ser lidos: as notas ficam "Aguardando" e são conferidas
            # no fim do envio, para não aparecer "sem contrato" por alguns minutos.
            db.evento(eid, "As notas serão conferidas quando as páginas deste envio terminarem de ser lidas.")
    return eid


# ---------------------------------------------------------------- processamento
class FalhaSimulada(Exception):
    pass


TENTATIVAS = 3  # falhas seguidas na mesma página antes de pulá-la


class Trabalhador(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.acordar = threading.Event()
        self.tentativas = {}  # (envio, página) -> falhas seguidas ao ler a página

    def run(self):
        try:
            ocr.aquecer()
        except Exception:
            pass  # sem o aquecimento, o modelo carrega na primeira página
        # Envios que estavam no meio quando o programa fechou: retomar de onde pararam.
        for e in db.q("SELECT * FROM envios WHERE status='processando'"):
            db.x("UPDATE envios SET status='fila', retomadas=retomadas+1 WHERE id=?", (e["id"],))
            db.evento(e["id"], f"O programa foi fechado no meio. Retomando da página {e['feitas'] + 1}, sem repetir as anteriores.")
        while True:
            e = db.q("SELECT * FROM envios WHERE status='fila' ORDER BY id LIMIT 1", um=True)
            if not e:
                self.acordar.wait(1.5)
                self.acordar.clear()
                continue
            try:
                self.processar(e)
            except FalhaSimulada as erro:
                self.falhou(e["id"], str(erro), automatico=True)
            except Exception as erro:  # qualquer falha real
                self.falhou(e["id"], f"{type(erro).__name__}: {erro}", automatico=True)

    def falhou(self, eid, msg, automatico):
        e = db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)
        db.x("UPDATE envios SET status='falhou', erro=? WHERE id=? AND status!='cancelado'", (msg, eid))
        db.evento(eid, f"Falha na página {e['feitas'] + 1}: {msg}. As {e['feitas']} páginas anteriores estão salvas.")
        if automatico:
            def retomar():
                time.sleep(4)
                atual = db.q("SELECT status FROM envios WHERE id=?", (eid,), um=True)
                if atual and atual["status"] == "falhou":
                    retomar_envio(eid, "Retomada automática")
                    self.acordar.set()
            threading.Thread(target=retomar, daemon=True).start()

    def processar(self, e):
        eid, ws = e["id"], e["ws"]
        cfg = db.get_config(ws)
        usar_claude = cfg.get("usar_claude") == "1"
        db.x("UPDATE envios SET status='processando', erro=NULL, motor=? WHERE id=?",
             ("claude" if usar_claude and analise.config.claude_configurado() else "local", eid))
        tipos = db.tipos_ws(ws)
        exemplos = db.q("SELECT * FROM exemplos WHERE ws=?", (ws,))
        pendentes = db.q("SELECT * FROM paginas WHERE envio_id=? AND status='pendente' ORDER BY n", (eid,))
        for p in pendentes:
            estado = db.q("SELECT status, falha_simulada FROM envios WHERE id=?", (eid,), um=True)
            if estado["status"] == "pausado":
                db.evento(eid, f"Pausado na página {p['n']}.")
                return
            if estado["status"] == "cancelado":
                return  # o evento já foi registrado por quem cancelou
            if estado["falha_simulada"]:
                db.x("UPDATE envios SET falha_simulada=0 WHERE id=?", (eid,))
                raise FalhaSimulada("queda simulada de conexão")
            anterior = db.q("SELECT tipo, pessoa, cpf FROM paginas WHERE envio_id=? AND n=?", (eid, p["n"] - 1), um=True)
            png = str(PAGINAS / f"{eid}_{p['n']:04d}.png")
            try:
                larg, alt, texto, linhas, fonte = ocr.renderizar(p["arquivo"], p["indice"], p["origem_tipo"], png)
                r = analise.analisar(png, texto, tipos, anterior, exemplos, usar_claude)
            except Exception as erro:
                # Falha passageira (ex.: rede): sobe, e a retomada automática tenta de novo. Se a mesma página
                # falhar TENTATIVAS vezes, ela é pulada; antes o envio ficava em falhou → fila para sempre.
                chave = (eid, p["n"])
                self.tentativas[chave] = self.tentativas.get(chave, 0) + 1
                if self.tentativas[chave] < TENTATIVAS:
                    raise
                del self.tentativas[chave]
                motivo = f"{type(erro).__name__}: {erro}"[:300]
                db.x("UPDATE paginas SET status='erro', sinais=? WHERE id=?",
                     (json.dumps([f"Não foi possível ler esta página ({motivo})"], ensure_ascii=False), p["id"]))
                db.x("UPDATE envios SET feitas=(SELECT COUNT(*) FROM paginas WHERE envio_id=? AND status IN ('feita','erro')) WHERE id=?",
                     (eid, eid))
                db.evento(eid, f"Página {p['n']} pulada depois de {TENTATIVAS} tentativas ({motivo}). As demais continuam.")
                continue
            db.x("""UPDATE paginas SET status='feita', img=?, largura=?, altura=?, texto=?, linhas=?, fonte_texto=?,
                    tipo=?, conf=?, inicio=?, sinais=?, candidatos=?, pessoa=?, cpf=?, empresa=?, sensiveis=?, motor=?
                    WHERE id=?""",
                 (png, larg, alt, texto, json.dumps(linhas, ensure_ascii=False), fonte, r["tipo"], r["conf"],
                  int(r["inicio"]), json.dumps(r["sinais"], ensure_ascii=False),
                  json.dumps(r["candidatos"], ensure_ascii=False), r["pessoa"], r["cpf"], r["empresa"],
                  json.dumps(r["sensiveis"], ensure_ascii=False), r["motor"], p["id"]))
            db.x("UPDATE envios SET feitas=(SELECT COUNT(*) FROM paginas WHERE envio_id=? AND status IN ('feita','erro')) WHERE id=?",
                 (eid, eid))
        agrupar(eid)
        conciliacao.extrair_envio(eid)
        r = conciliacao.conciliar(ws)
        db.x("UPDATE envios SET status='concluido', terminado_em=? WHERE id=?", (db.agora(), eid))
        n_docs = db.q("SELECT COUNT(*) c FROM docs WHERE envio_id=?", (eid,), um=True)["c"]
        n_rev = db.q("SELECT COUNT(*) c FROM docs WHERE envio_id=? AND status='revisao'", (eid,), um=True)["c"]
        db.evento(eid, f"Concluído: {n_docs} documentos separados, {n_rev} para confirmar. "
                       f"Conciliação: {r['com_divergencia']} de {r['notas']} nota(s) com divergência.")


def retomar_envio(eid, motivo="Retomado"):
    e = db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)
    if not e or e["status"] not in ("falhou", "pausado"):
        return False
    db.x("UPDATE envios SET status='fila', retomadas=retomadas+1 WHERE id=?", (eid,))
    db.evento(eid, f"{motivo}: continua da página {e['feitas'] + 1} (as anteriores já estavam salvas).")
    return True


# ------------------------------------------------------------------ agrupamento
def _chave_texto(texto: str) -> str:
    return "".join(ch for ch in analise.norm(texto or "") if ch.isalnum())


def integridade(pags: list[dict], todas: list[dict] | None = None) -> list[str]:
    """Problemas do documento pela numeração ("3 de 9") e pelo texto: página repetida, páginas faltando,
    página escaneada duas vezes. Lista vazia = documento inteiro."""
    problemas = []
    nums = [(p, analise.extrair_basico(p["texto"] or "")["pag"]) for p in pags]
    com_num = [(p, k) for p, k in nums if k]
    if com_num:
        totais = [k[1] for _, k in com_num]
        n = max(set(totais), key=totais.count)
        vistos = {}
        for p, (k, tot) in com_num:
            if tot == n and 1 <= k <= n:
                vistos.setdefault(k, []).append(p["n"])
        for k, onde in sorted(vistos.items()):
            if len(onde) > 1:
                problemas.append(f"Página repetida: a página {k} de {n} aparece {len(onde)} vezes (págs. {', '.join(map(str, onde))} do lote)")
        faltam = [k for k in range(1, n + 1) if k not in vistos]
        sem_num = len(pags) - len(com_num)  # páginas ilegíveis podem ser justamente as que "faltam"
        if faltam and len(faltam) > sem_num and len(com_num) >= max(2, len(pags) // 2):
            lista = ", ".join(map(str, faltam[:6])) + ("…" if len(faltam) > 6 else "")
            problemas.append(f"Documento incompleto: falta{'m' if len(faltam) > 1 else ''} a{'s' if len(faltam) > 1 else ''} página{'s' if len(faltam) > 1 else ''} {lista} de {n}")
    # Mesma folha escaneada duas vezes (texto praticamente igual, sem depender da numeração).
    chaves = {}
    for p in (todas or pags):
        c = _chave_texto(p["texto"])
        if len(c) >= 200:
            chaves.setdefault(c, []).append(p["n"])
    meus = {p["n"] for p in pags}
    for onde in chaves.values():
        if len(onde) > 1 and meus & set(onde[1:]):
            texto = f"Página escaneada duas vezes: o conteúdo das págs. {', '.join(map(str, onde))} do lote é igual"
            if not any(texto[:40] in x or "Página repetida" in x for x in problemas):
                problemas.append(texto)
    return problemas


def atualizar_subtipo(did: int, forcar: bool = False) -> dict | None:
    """Calcula o subtipo para o documento inteiro; preserva correção humana."""
    doc = db.q("SELECT envio_id, pag_ini, pag_fim, tipo, subtipo_manual FROM docs WHERE id=?",
               (did,), um=True)
    if not doc:
        return None
    if doc["subtipo_manual"] and not forcar:
        return None
    paginas = db.q("""SELECT texto FROM paginas WHERE envio_id=?
                       AND n BETWEEN ? AND ? AND status='feita' ORDER BY n""",
                   (doc["envio_id"], doc["pag_ini"], doc["pag_fim"]))
    texto = "\n".join(p["texto"] or "" for p in paginas)
    resultado = identificar_subtipo(texto)
    # Divergência entre a classificação existente e o subtipo exige revisão,
    # mas não interrompe a conciliação atual.
    esperado = TIPO_COMPATIVEL.get(resultado["subtipo"])
    if esperado and doc["tipo"] not in (esperado, "Não identificado"):
        resultado["revisao_necessaria"] = True
        resultado["evidencias"].append("Divergência em relação ao tipo principal: " + doc["tipo"])
    db.x("""UPDATE docs SET subtipo=?, subtipo_pontos=?, subtipo_evidencias=?,
           subtipo_alternativas=?, subtipo_revisao=?, subtipo_manual=0 WHERE id=?""",
         (resultado["subtipo"], resultado["pontuacao"],
          json.dumps(resultado["evidencias"], ensure_ascii=False),
          json.dumps(resultado["alternativas"], ensure_ascii=False),
          int(resultado["revisao_necessaria"]), did))
    return resultado


def _doc_de_paginas(eid, ws, pags, limiar, todas=None):
    tipo = pags[0]["tipo"]
    confs = [p["conf"] for p in pags]
    conf = min(confs)
    fraca = pags[confs.index(conf)]
    tipos_dif = {p["tipo"] for p in pags}
    duvida = "tipo"
    if len(pags) > 1 and (fraca is not pags[0] or len(tipos_dif) > 1):
        duvida = "fronteira"
    if tipo == "Não identificado":
        duvida = "tipo"
    status = "revisao" if conf < limiar or tipo == "Não identificado" else "confirmado"
    problemas = integridade(pags, todas)
    sinais_fraca = fraca["sinais"]
    motivo = f"página {fraca['n']}"
    if problemas:
        # Documento com página repetida ou faltando: uma pessoa decide antes de entrar na conferência.
        conf, status, duvida = min(conf, 55), "revisao", "integridade"
        sinais_fraca = json.dumps(problemas + json.loads(fraca["sinais"] or "[]"), ensure_ascii=False)
        motivo = problemas[0]
    def primeiro(campo):
        return next((p[campo] for p in pags if p[campo]), None)
    sens = []
    for p in pags:
        sens += json.loads(p["sensiveis"] or "[]")
    did = db.x("""INSERT INTO docs(envio_id, ws, tipo, conf, pag_ini, pag_fim, pessoa, cpf, empresa, status, duvida,
                motivo, sinais, candidatos, sensiveis, criado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (eid, ws, tipo, conf, pags[0]["n"], pags[-1]["n"], primeiro("pessoa"), primeiro("cpf"),
                primeiro("empresa"), status, duvida, motivo, sinais_fraca,
                pags[0]["candidatos"], json.dumps(sens, ensure_ascii=False), db.agora()))
    db.x("UPDATE paginas SET doc_id=? WHERE envio_id=? AND n BETWEEN ? AND ?", (did, eid, pags[0]["n"], pags[-1]["n"]))
    texto = "\n".join(p["texto"] or "" for p in pags)
    db.x("INSERT INTO busca(doc_id, ws, texto) VALUES(?,?,?)", (did, ws, texto))
    atualizar_subtipo(did)
    return did


def agrupar(eid):
    e = db.q("SELECT * FROM envios WHERE id=?", (eid,), um=True)
    limiar = int(db.get_config(e["ws"])["limiar"])
    for d in db.q("SELECT id FROM docs WHERE envio_id=?", (eid,)):
        db.x("DELETE FROM busca WHERE doc_id=?", (d["id"],))
    db.x("DELETE FROM docs WHERE envio_id=?", (eid,))
    pags = db.q("SELECT * FROM paginas WHERE envio_id=? AND status='feita' ORDER BY n", (eid,))
    grupo = []
    for p in pags:
        if grupo and p["inicio"]:
            _doc_de_paginas(eid, e["ws"], grupo, limiar, pags)
            grupo = []
        grupo.append(p)
    if grupo:
        _doc_de_paginas(eid, e["ws"], grupo, limiar, pags)


def reindexar_doc(did):
    d = db.q("SELECT * FROM docs WHERE id=?", (did,), um=True)
    pags = db.q("SELECT texto FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n",
                (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    db.x("DELETE FROM busca WHERE doc_id=?", (did,))
    db.x("INSERT INTO busca(doc_id, ws, texto) VALUES(?,?,?)", (did, d["ws"], "\n".join(p["texto"] or "" for p in pags)))
    db.x("UPDATE paginas SET doc_id=? WHERE envio_id=? AND n BETWEEN ? AND ?", (did, d["envio_id"], d["pag_ini"], d["pag_fim"]))
    atualizar_subtipo(did, forcar=True)


def aprender(ws, tipo, did):
    """Guarda as palavras do documento confirmado como exemplo do tipo (ajuda os próximos)."""
    d = db.q("SELECT * FROM docs WHERE id=?", (did,), um=True)
    p = db.q("SELECT texto FROM paginas WHERE envio_id=? AND n=?", (d["envio_id"], d["pag_ini"]), um=True)
    pal = sorted(analise.palavras(p["texto"] if p else ""))
    if len(pal) >= 8:
        db.x("INSERT INTO exemplos(ws, tipo, palavras) VALUES(?,?,?)", (ws, tipo, json.dumps(pal[:400])))
