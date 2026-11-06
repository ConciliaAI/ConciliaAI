"""Conciliação: guarda notas, contratos e aditivos e cruza cada nota com o contrato do fornecedor.

As regras são código, não opinião da IA: cada divergência diz qual regra falhou, o valor esperado
e o valor encontrado. A IA só ajuda a ler os documentos. Quem decide é a pessoa na revisão.
"""
import json
import re

from . import analise, db, fiscal
from .fiscal import TIPO_ADITIVO, TIPO_CONTRATO, TIPO_NOTA, brl, fmt_cnpj, fmt_data

REGRAS = {
    "SEM_CONTRATO": ("Fornecedor sem contrato", "critica"),
    "VALOR_DIVERGENTE": ("Valor acima do contratado", "alta"),
    "FORA_VIGENCIA": ("Nota fora da vigência do contrato", "alta"),
    "NOTA_DUPLICADA": ("Nota possivelmente duplicada", "alta"),
    "SERVICO_DIVERGENTE": ("Serviço diferente do contratado", "media"),
    "TOMADOR_DIVERGENTE": ("Nota emitida para outro tomador", "media"),
}
PALAVRAS_VAZIAS = {"servico", "servicos", "prestacao", "contrato", "mensal", "referente", "para", "com", "sem",
                   "conforme", "periodo", "mes", "nota", "fiscal", "demais", "geral", "gerais"}


# ------------------------------------------------------------------ cadastro
def fornecedor(ws: str, cnpj: str, nome: str | None = None) -> int | None:
    cnpj = fiscal.so_digitos(cnpj)
    if not cnpj:
        return None
    f = db.q("SELECT * FROM fornecedores WHERE ws=? AND cnpj=?", (ws, cnpj), um=True)
    if f:
        if nome and not f["nome"]:
            db.x("UPDATE fornecedores SET nome=? WHERE id=?", (nome, f["id"]))
        return f["id"]
    return db.x("INSERT INTO fornecedores(ws, cnpj, nome, criado_em) VALUES(?,?,?,?)", (ws, cnpj, nome, db.agora()))


def salvar_nota(ws: str, n: dict, origem: str, envio_id: int | None, doc_id: int | None = None,
                xml: str | None = None) -> tuple[int, bool]:
    """Grava ou atualiza a nota. A mesma nota (prestador + número + data) enviada de novo não vira outra.
    Devolve (id, nova?)."""
    cnpj = fiscal.so_digitos(n.get("cnpj_prestador"))
    atual = None
    if n.get("chave"):
        atual = db.q("SELECT * FROM notas WHERE ws=? AND chave=?", (ws, n["chave"]), um=True)
    if not atual and n.get("data_emissao"):
        atual = db.q("SELECT * FROM notas WHERE ws=? AND cnpj_prestador=? AND numero=? AND data_emissao=?",
                     (ws, cnpj, str(n["numero"]), n["data_emissao"]), um=True)
    if not atual and not n.get("data_emissao") and n.get("valor") is not None:
        atual = db.q("SELECT * FROM notas WHERE ws=? AND cnpj_prestador=? AND numero=? AND valor=?",
                     (ws, cnpj, str(n["numero"]), n["valor"]), um=True)
    if not atual and origem == "pdf" and n.get("data_emissao") and n.get("valor") is not None:
        # PDF digitalizado com o número mal lido: se já existe o XML do mesmo prestador, data e valor, é a mesma nota.
        atual = db.q("SELECT * FROM notas WHERE ws=? AND cnpj_prestador=? AND data_emissao=? AND valor=? AND origem='xml'",
                     (ws, cnpj, n["data_emissao"], n["valor"]), um=True)
    fid = fornecedor(ws, cnpj, n.get("nome_prestador"))
    campos = {"fornecedor_id": fid, "cnpj_prestador": cnpj, "numero": str(n.get("numero")),
              "chave": n.get("chave"), "data_emissao": n.get("data_emissao"), "competencia": n.get("competencia"),
              "nome_prestador": n.get("nome_prestador"), "cnpj_tomador": fiscal.so_digitos(n.get("cnpj_tomador")) or None,
              "descricao": n.get("descricao"), "codigo_servico": n.get("codigo_servico"), "valor": n.get("valor"),
              "valor_liquido": n.get("valor_liquido"), "contrato_ref": n.get("contrato_ref"), "formato": n.get("formato")}
    if atual:
        if atual["origem"] == "xml" and origem == "pdf":
            # O XML é a fonte oficial; o PDF só fica como evidência.
            if doc_id:
                db.x("UPDATE notas SET doc_id=COALESCE(doc_id, ?) WHERE id=?", (doc_id, atual["id"]))
            return atual["id"], False
        sets = {k: v for k, v in campos.items() if v not in (None, "")}
        sets.update({"origem": origem, "envio_id": envio_id or atual["envio_id"]})
        if doc_id:
            sets["doc_id"] = doc_id
        if xml:
            sets["xml"] = xml
        db.x(f"UPDATE notas SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), atual["id"]))
        return atual["id"], False
    campos.update({"ws": ws, "origem": origem, "envio_id": envio_id, "doc_id": doc_id, "xml": xml,
                   "status": "pendente", "criado_em": db.agora()})
    nid = db.x(f"INSERT INTO notas({', '.join(campos)}) VALUES({', '.join('?' * len(campos))})", tuple(campos.values()))
    return nid, True


def salvar_contrato(ws: str, c: dict, doc_id: int | None, envio_id: int | None) -> int | None:
    cnpj = fiscal.so_digitos(c.get("cnpj_prestador"))
    if not cnpj:
        return None
    atual = None
    if c.get("numero"):
        atual = db.q("SELECT * FROM contratos WHERE ws=? AND cnpj_prestador=? AND numero=?", (ws, cnpj, c["numero"]), um=True)
    if not atual and doc_id:
        atual = db.q("SELECT * FROM contratos WHERE ws=? AND doc_id=?", (ws, doc_id), um=True)
    fid = fornecedor(ws, cnpj, c.get("nome_prestador"))
    campos = {"fornecedor_id": fid, "cnpj_prestador": cnpj, "numero": c.get("numero"),
              "nome_prestador": c.get("nome_prestador"), "cnpj_tomador": fiscal.so_digitos(c.get("cnpj_tomador")) or None,
              "objeto": c.get("objeto"), "valor_mensal": c.get("valor_mensal"), "valor_total": c.get("valor_total"),
              "vigencia_inicio": c.get("vigencia_inicio"), "vigencia_fim": c.get("vigencia_fim"),
              "doc_id": doc_id, "envio_id": envio_id}
    if atual:
        sets = {k: v for k, v in campos.items() if v not in (None, "")}
        db.x(f"UPDATE contratos SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), atual["id"]))
        return atual["id"]
    campos.update({"ws": ws, "criado_em": db.agora()})
    return db.x(f"INSERT INTO contratos({', '.join(campos)}) VALUES({', '.join('?' * len(campos))})", tuple(campos.values()))


def salvar_aditivo(ws: str, a: dict, doc_id: int | None, envio_id: int | None) -> int | None:
    if not (a.get("numero") or a.get("contrato_ref")):
        return None
    atual = db.q("SELECT * FROM aditivos WHERE ws=? AND numero IS ? AND contrato_ref IS ?",
                 (ws, a.get("numero"), a.get("contrato_ref")), um=True)
    campos = {"numero": a.get("numero"), "contrato_ref": a.get("contrato_ref"),
              "cnpj_prestador": fiscal.so_digitos(a.get("cnpj_prestador")) or None,
              "valor_adicional": a.get("valor_adicional"), "vigencia_inicio": a.get("vigencia_inicio"),
              "vigencia_fim": a.get("vigencia_fim"), "doc_id": doc_id, "envio_id": envio_id}
    if atual:
        sets = {k: v for k, v in campos.items() if v not in (None, "")}
        db.x(f"UPDATE aditivos SET {', '.join(k + '=?' for k in sets)} WHERE id=?", (*sets.values(), atual["id"]))
        return atual["id"]
    campos.update({"ws": ws, "criado_em": db.agora()})
    return db.x(f"INSERT INTO aditivos({', '.join(campos)}) VALUES({', '.join('?' * len(campos))})", tuple(campos.values()))


# ----------------------------------------------------- documentos já separados
def extrair_doc(did: int) -> str | None:
    """Lê os campos de um documento confirmado (contrato, aditivo ou nota em PDF) e guarda. Devolve um aviso, se houver."""
    d = db.q("SELECT * FROM docs WHERE id=?", (did,), um=True)
    if not d or d["status"] not in ("confirmado", "revisao") or d["tipo"] not in fiscal.TIPOS_FISCAIS:
        return None
    pags = db.q("SELECT texto FROM paginas WHERE envio_id=? AND n BETWEEN ? AND ? ORDER BY n",
                (d["envio_id"], d["pag_ini"], d["pag_fim"]))
    texto = "\n".join(p["texto"] or "" for p in pags)
    if d["status"] == "revisao":
        # Ainda em dúvida: lê os campos só para mostrar (ex.: "contrato aguardando confirmação"), sem usar na conferência.
        dados = fiscal.extrair_local(d["tipo"], texto)
        db.x("UPDATE docs SET dados=? WHERE id=?",
             (json.dumps({"campos": dados, "motor": "local", "provisorio": True}, ensure_ascii=False), did))
        return None
    usar = db.get_config(d["ws"]).get("usar_claude") == "1"
    dados, motor = fiscal.extrair(d["tipo"], texto, usar)
    aviso = None
    if d["tipo"] == TIPO_NOTA:
        ok = dados.get("numero") and dados.get("valor") is not None and fiscal.cnpj_valido(dados.get("cnpj_prestador"))
        if ok:
            salvar_nota(d["ws"], dados, "pdf", d["envio_id"], doc_id=did)
        else:
            aviso = "Nota em PDF sem número, valor ou CNPJ legível: não entrou na conciliação. Envie o XML."
    elif d["tipo"] == TIPO_CONTRATO:
        if not salvar_contrato(d["ws"], dados, did, d["envio_id"]):
            aviso = "Contrato sem CNPJ da contratada legível: não entrou na conciliação."
    elif d["tipo"] == TIPO_ADITIVO:
        if not salvar_aditivo(d["ws"], dados, did, d["envio_id"]):
            aviso = "Aditivo sem número nem contrato de referência legíveis."
    db.x("UPDATE docs SET dados=?, aviso=? WHERE id=?",
         (json.dumps({"campos": dados, "motor": motor}, ensure_ascii=False), aviso, did))
    return aviso


def extrair_envio(eid: int):
    for d in db.q("SELECT id FROM docs WHERE envio_id=? AND status IN ('confirmado','revisao')", (eid,)):
        extrair_doc(d["id"])


# ------------------------------------------------------------------ regras
def _palavras(s: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z]{4,}", analise.norm(s or "")) if w not in PALAVRAS_VAZIAS}


def _mesmo_servico(objeto: str, descricao: str) -> bool:
    """Há palavra em comum? Também compara sem espaços: o OCR cola palavras ("Servicosderecepcao")."""
    a, b = _palavras(objeto), _palavras(descricao)
    if a & b:
        return True
    colado_a = re.sub(r"[^a-z]", "", analise.norm(objeto))
    colado_b = re.sub(r"[^a-z]", "", analise.norm(descricao))
    return any(w in colado_a for w in b if len(w) >= 5) or any(w in colado_b for w in a if len(w) >= 5)


def _no_periodo(dia, ini, fim) -> bool:
    return bool(dia) and (not ini or dia >= ini) and (not fim or dia <= fim)


def _contrato_da_nota(nota, contratos):
    candidatos = [c for c in contratos if c["cnpj_prestador"] == nota["cnpj_prestador"]]
    if not candidatos:
        return None
    if nota.get("contrato_ref"):
        ref = analise.chave_nome(nota["contrato_ref"])
        for c in candidatos:
            if c["numero"] and analise.chave_nome(c["numero"]) == ref:
                return c
    vigentes = [c for c in candidatos if _no_periodo(nota["data_emissao"], c["vigencia_inicio"], c["vigencia_fim"])]
    escolha = vigentes or candidatos
    return sorted(escolha, key=lambda c: c["vigencia_fim"] or "", reverse=True)[0]


def _aditivos_do_contrato(contrato, aditivos):
    num = analise.chave_nome(contrato["numero"] or "")
    return [a for a in aditivos if (num and analise.chave_nome(a["contrato_ref"] or "") == num)
            or (not a["contrato_ref"] and a["cnpj_prestador"] == contrato["cnpj_prestador"])]


def avaliar_nota(nota: dict, contratos: list, aditivos: list, notas: list, tolerancia: float) -> tuple[list, dict | None, str | None]:
    """Devolve (divergências, contrato usado, observação)."""
    achados, obs = [], None
    nome = nota.get("nome_prestador") or fmt_cnpj(nota["cnpj_prestador"])
    # Duplicidade: mesmo prestador e mesmo número em outra nota.
    for outra in notas:
        if (outra["id"] != nota["id"] and outra["cnpj_prestador"] == nota["cnpj_prestador"]
                and outra["numero"] == nota["numero"]
                and ((outra["data_emissao"] or ""), outra["id"]) < ((nota["data_emissao"] or ""), nota["id"])):
            achados.append(("NOTA_DUPLICADA", f"O número {nota['numero']} já aparece na nota emitida em {fmt_data(outra['data_emissao'])} pelo mesmo prestador.",
                            "Número de nota único por prestador", f"Repete a nota de {fmt_data(outra['data_emissao'])} ({brl(outra['valor'])})"))
            break
    c = _contrato_da_nota(nota, contratos)
    if not c:
        achados.append(("SEM_CONTRATO", f"Não há contrato cadastrado para {nome} (CNPJ {fmt_cnpj(nota['cnpj_prestador'])}).",
                        "Contrato ativo com o prestador", "Nenhum contrato encontrado"))
        return achados, None, obs
    periodo = f"{fmt_data(c['vigencia_inicio'])} a {fmt_data(c['vigencia_fim'])}"
    if (c["vigencia_inicio"] or c["vigencia_fim"]) and nota["data_emissao"] and not _no_periodo(nota["data_emissao"], c["vigencia_inicio"], c["vigencia_fim"]):
        achados.append(("FORA_VIGENCIA", f"Nota emitida em {fmt_data(nota['data_emissao'])}, fora da vigência do contrato {c['numero'] or ''} ({periodo}).",
                        f"Emissão entre {periodo}", fmt_data(nota["data_emissao"])))
    if c["valor_mensal"] and nota["valor"] is not None:
        base = c["valor_mensal"] * (1 + tolerancia / 100)
        ads = _aditivos_do_contrato(c, aditivos)
        vigentes = [a for a in ads if a["valor_adicional"] and _no_periodo(nota["data_emissao"], a["vigencia_inicio"], a["vigencia_fim"])]
        fora = [a for a in ads if a["valor_adicional"] and a not in vigentes]
        limite = base + sum(a["valor_adicional"] for a in vigentes)
        if nota["valor"] > limite + 0.009:
            msg = f"A nota cobra {brl(nota['valor'])}, mas o contrato {c['numero'] or ''} prevê {brl(c['valor_mensal'])} por mês"
            if vigentes:
                msg += f" mais {brl(sum(a['valor_adicional'] for a in vigentes))} de aditivo vigente"
            msg += f". Diferença de {brl(nota['valor'] - limite)}."
            if fora:
                a = fora[0]
                msg += f" O aditivo {a['numero'] or ''} (+{brl(a['valor_adicional'])}) não estava vigente na data da nota ({fmt_data(a['vigencia_inicio'])} a {fmt_data(a['vigencia_fim'])})."
            esperado = f"Até {brl(limite)}" + (f" (com tolerância de {tolerancia:g}%)" if tolerancia else "")
            achados.append(("VALOR_DIVERGENTE", msg, esperado, brl(nota["valor"])))
        elif nota["valor"] > base + 0.009 and vigentes:
            obs = f"Valor acima do mensal coberto pelo aditivo {', '.join(a['numero'] or '' for a in vigentes)} (vigente na data da nota)."
    if c["objeto"] and nota.get("descricao"):
        if not _mesmo_servico(c["objeto"], nota["descricao"]):
            achados.append(("SERVICO_DIVERGENTE", f"A nota descreve “{nota['descricao']}”, mas o objeto do contrato é “{c['objeto']}”.",
                            c["objeto"], nota["descricao"]))
    if c["cnpj_tomador"] and nota.get("cnpj_tomador") and c["cnpj_tomador"] != nota["cnpj_tomador"]:
        achados.append(("TOMADOR_DIVERGENTE", f"A nota foi emitida para o CNPJ {fmt_cnpj(nota['cnpj_tomador'])}, mas o contratante é {fmt_cnpj(c['cnpj_tomador'])}.",
                        fmt_cnpj(c["cnpj_tomador"]), fmt_cnpj(nota["cnpj_tomador"])))
    return achados, c, obs


def conciliar(ws: str) -> dict:
    """Refaz o cruzamento de todas as notas do cliente. Decisões humanas já tomadas são mantidas."""
    contratos = db.q("SELECT * FROM contratos WHERE ws=?", (ws,))
    aditivos = db.q("SELECT * FROM aditivos WHERE ws=?", (ws,))
    notas = db.q("SELECT * FROM notas WHERE ws=? ORDER BY id", (ws,))
    tol = float(db.get_config(ws).get("tolerancia", "0") or 0)
    # Documentos ainda em "Dúvidas da leitura" podem ser o contrato que falta: não acusar "sem contrato" antes disso.
    em_duvida = db.q("SELECT COUNT(*) c FROM docs WHERE ws=? AND status='revisao'", (ws,), um=True)["c"]
    abertas = 0
    for nota in notas:
        achados, c, obs = avaliar_nota(nota, contratos, aditivos, notas, tol)
        esperando = False
        if em_duvida and any(a[0] == "SEM_CONTRATO" for a in achados):
            achados = [a for a in achados if a[0] != "SEM_CONTRATO"]
            esperando = True
            obs = f"Contrato ainda não encontrado: há {em_duvida} documento(s) em Dúvidas da leitura. A nota é conferida depois da confirmação."
        existentes = {d["regra"]: d for d in db.q("SELECT * FROM divergencias WHERE nota_id=?", (nota["id"],))}
        vistas = set()
        for regra, msg, esperado, encontrado in achados:
            vistas.add(regra)
            sev = REGRAS[regra][1]
            if regra in existentes:
                db.x("UPDATE divergencias SET mensagem=?, esperado=?, encontrado=?, contrato_id=? WHERE id=?",
                     (msg, esperado, encontrado, c["id"] if c else None, existentes[regra]["id"]))
            else:
                db.x("""INSERT INTO divergencias(ws, nota_id, contrato_id, fornecedor_id, regra, severidade, mensagem,
                        esperado, encontrado, status, criado_em) VALUES(?,?,?,?,?,?,?,?,?, 'aberta', ?)""",
                     (ws, nota["id"], c["id"] if c else None, nota["fornecedor_id"], regra, sev, msg, esperado,
                      encontrado, db.agora()))
        for regra, d in existentes.items():
            if regra not in vistas and d["status"] == "aberta":
                db.x("DELETE FROM divergencias WHERE id=?", (d["id"],))
        sts = [d["status"] for d in db.q("SELECT status FROM divergencias WHERE nota_id=?", (nota["id"],))]
        if "aberta" in sts:
            status = "divergente"
            abertas += 1
        elif "rejeitada" in sts:
            status = "rejeitada"
        elif "aprovada" in sts:
            status = "aprovada"
        elif esperando:
            status = "pendente"
        else:
            status = "conciliada"
        db.x("UPDATE notas SET contrato_id=?, status=?, observacao=? WHERE id=?",
             (c["id"] if c else None, status, obs, nota["id"]))
    return {"notas": len(notas), "com_divergencia": abertas}


# ------------------------------------------------------------------ decisão humana
def decidir(div_id: int, acao: str, comentario: str, usuario: str) -> dict:
    d = db.q("SELECT * FROM divergencias WHERE id=?", (div_id,), um=True)
    if not d:
        raise LookupError("Divergência não encontrada")
    status = {"aprovar": "aprovada", "rejeitar": "rejeitada", "reabrir": "aberta"}.get(acao)
    if not status:
        raise ValueError("Ação desconhecida")
    if status == "aberta":
        db.x("UPDATE divergencias SET status='aberta', decidido_por=NULL, decidido_em=NULL, comentario=NULL WHERE id=?", (div_id,))
    else:
        db.x("UPDATE divergencias SET status=?, decidido_por=?, decidido_em=?, comentario=? WHERE id=?",
             (status, usuario, db.agora(), comentario or None, div_id))
    nota = db.q("SELECT numero, nome_prestador FROM notas WHERE id=?", (d["nota_id"],), um=True)
    verbo = {"aprovada": "aprovou", "rejeitada": "rejeitou", "aberta": "reabriu"}[status]
    db.trilha(d["ws"], usuario, f"{verbo} “{REGRAS[d['regra']][0]}” da nota {nota['numero'] if nota else '?'}"
              + (f": {comentario}" if comentario else ""))
    conciliar(d["ws"])
    return {"ok": True, "status": status}


# ------------------------------------------------------------- acerto com gabarito
MAPA_REGRAS_GABARITO = {
    "R02_VALOR_DIVERGENTE": "VALOR_DIVERGENTE", "ADITIVO_FORA_VIGENCIA": "VALOR_DIVERGENTE",
    "R04_SERVICO_DIVERGENTE": "SERVICO_DIVERGENTE", "R05_FORA_VIGENCIA": "FORA_VIGENCIA",
    "R07_DUPLICADA": "NOTA_DUPLICADA", "SEM_CONTRATO": "SEM_CONTRATO",
}


def medir(ws: str, gabarito: dict) -> dict:
    """Compara as divergências encontradas com as esperadas no gabarito do gerador sintético."""
    notas = db.q("SELECT * FROM notas WHERE ws=?", (ws,))
    idx = {(n["cnpj_prestador"], n["numero"], n["data_emissao"]): n for n in notas}
    vp = fp = fn = vn = regra_ok = encontradas = 0
    erros = []
    for inv in gabarito["invoices"]:
        n = idx.get((fiscal.so_digitos(inv["prestador_cnpj"]), str(inv["numero"]), inv["data_emissao"]))
        esperadas = {MAPA_REGRAS_GABARITO[r] for r in inv.get("scenario_reasons", []) if r in MAPA_REGRAS_GABARITO}
        if not n:
            fn += bool(esperadas)
            erros.append({"nota": inv["invoice_id"], "esperado": ", ".join(sorted(esperadas)) or "sem divergência",
                          "encontrado": "nota não foi lida"})
            continue
        encontradas += 1
        achadas = {d["regra"] for d in db.q("SELECT regra FROM divergencias WHERE nota_id=?", (n["id"],))}
        if esperadas and achadas:
            vp += 1
            regra_ok += esperadas <= achadas
        elif esperadas:
            fn += 1
        elif achadas:
            fp += 1
        else:
            vn += 1
        if esperadas != achadas:
            erros.append({"nota": inv["invoice_id"], "esperado": ", ".join(sorted(esperadas)) or "sem divergência",
                          "encontrado": ", ".join(sorted(achadas)) or "sem divergência"})
    pct = lambda a, b: round(100 * a / b, 1) if b else 0.0
    total = len(gabarito["invoices"])
    return {"notas_gabarito": total, "notas_lidas": encontradas, "pct_lidas": pct(encontradas, total),
            "divergencias_esperadas": vp + fn, "detectadas": vp, "falsos_alarmes": fp,
            "precisao": pct(vp, vp + fp), "cobertura": pct(vp, vp + fn), "regra_certa": pct(regra_ok, vp),
            "corretas_sem_alerta": vn, "erros": erros[:20], "total_erros": len(erros)}
