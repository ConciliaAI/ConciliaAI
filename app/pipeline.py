"""Fila de envios: processa página por página, salva cada uma (ponto de retomada) e agrupa em documentos."""
import hashlib
import json
import threading
import time
import zipfile
from pathlib import Path

from . import analise, conciliacao, config, db, fiscal, ocr
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
            with zipfile.ZipFile(caminho) as z:
                for j, info in enumerate(sorted(z.infolist(), key=lambda k: k.filename)):
                    if info.is_dir() or not info.filename.lower().endswith(EXTS + (".xml",)):
                        continue
                    nome_z = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(info.filename).name)
                    destino = pasta / f"{i:03d}_{j:03d}_{nome_z}"
                    destino.write_bytes(z.read(info))
                    (xmls if nome_z.lower().endswith(".xml") else salvos).append(destino)
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


class Trabalhador(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.acordar = threading.Event()

    def run(self):
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
        db.x("UPDATE envios SET status='falhou', erro=? WHERE id=?", (msg, eid))
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
            if estado["falha_simulada"]:
                db.x("UPDATE envios SET falha_simulada=0 WHERE id=?", (eid,))
                raise FalhaSimulada("queda simulada de conexão")
            anterior = db.q("SELECT tipo, pessoa, cpf FROM paginas WHERE envio_id=? AND n=?", (eid, p["n"] - 1), um=True)
            png = str(PAGINAS / f"{eid}_{p['n']:04d}.png")
            larg, alt, texto, linhas, fonte = ocr.renderizar(p["arquivo"], p["indice"], p["origem_tipo"], png)
            r = analise.analisar(png, texto, tipos, anterior, exemplos, usar_claude)
            db.x("""UPDATE paginas SET status='feita', img=?, largura=?, altura=?, texto=?, linhas=?, fonte_texto=?,
                    tipo=?, conf=?, inicio=?, sinais=?, candidatos=?, pessoa=?, cpf=?, empresa=?, sensiveis=?, motor=?
                    WHERE id=?""",
                 (png, larg, alt, texto, json.dumps(linhas, ensure_ascii=False), fonte, r["tipo"], r["conf"],
                  int(r["inicio"]), json.dumps(r["sinais"], ensure_ascii=False),
                  json.dumps(r["candidatos"], ensure_ascii=False), r["pessoa"], r["cpf"], r["empresa"],
                  json.dumps(r["sensiveis"], ensure_ascii=False), r["motor"], p["id"]))
            db.x("UPDATE envios SET feitas=(SELECT COUNT(*) FROM paginas WHERE envio_id=? AND status='feita') WHERE id=?",
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
def _doc_de_paginas(eid, ws, pags, limiar):
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
    def primeiro(campo):
        return next((p[campo] for p in pags if p[campo]), None)
    sens = []
    for p in pags:
        sens += json.loads(p["sensiveis"] or "[]")
    did = db.x("""INSERT INTO docs(envio_id, ws, tipo, conf, pag_ini, pag_fim, pessoa, cpf, empresa, status, duvida,
                motivo, sinais, candidatos, sensiveis, criado_em) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (eid, ws, tipo, conf, pags[0]["n"], pags[-1]["n"], primeiro("pessoa"), primeiro("cpf"),
                primeiro("empresa"), status, duvida, f"página {fraca['n']}", fraca["sinais"],
                pags[0]["candidatos"], json.dumps(sens, ensure_ascii=False), db.agora()))
    db.x("UPDATE paginas SET doc_id=? WHERE envio_id=? AND n BETWEEN ? AND ?", (did, eid, pags[0]["n"], pags[-1]["n"]))
    texto = "\n".join(p["texto"] or "" for p in pags)
    db.x("INSERT INTO busca(doc_id, ws, texto) VALUES(?,?,?)", (did, ws, texto))
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
            _doc_de_paginas(eid, e["ws"], grupo, limiar)
            grupo = []
        grupo.append(p)
    if grupo:
        _doc_de_paginas(eid, e["ws"], grupo, limiar)


def reindexar_doc(did):
    d = db.q("SELECT * FROM docs WHERE id=?", (did,), um=True)
    pags = db.q("SELECT texto FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n",
                (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    db.x("DELETE FROM busca WHERE doc_id=?", (did,))
    db.x("INSERT INTO busca(doc_id, ws, texto) VALUES(?,?,?)", (did, d["ws"], "\n".join(p["texto"] or "" for p in pags)))
    db.x("UPDATE paginas SET doc_id=? WHERE envio_id=? AND n BETWEEN ? AND ?", (did, d["envio_id"], d["pag_ini"], d["pag_fim"]))


def aprender(ws, tipo, did):
    """Guarda as palavras do documento confirmado como exemplo do tipo (ajuda os próximos)."""
    d = db.q("SELECT * FROM docs WHERE id=?", (did,), um=True)
    p = db.q("SELECT texto FROM paginas WHERE envio_id=? AND n=?", (d["envio_id"], d["pag_ini"]), um=True)
    pal = sorted(analise.palavras(p["texto"] if p else ""))
    if len(pal) >= 8:
        db.x("INSERT INTO exemplos(ws, tipo, palavras) VALUES(?,?,?)", (ws, tipo, json.dumps(pal[:400])))
