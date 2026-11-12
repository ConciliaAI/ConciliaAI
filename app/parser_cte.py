"""Parser específico para CT-e modelo 57: participantes, transporte e documentos vinculados."""
from .fiscal_xml_comum import (
    XMLFiscalErro, abrir, unico, filho, filhos, texto, decimal, guardar,
    guardar_decimal, resultado_base, identificador, chave_status, protocolo, local
)


def ler_cte(conteudo: bytes):
    raiz = abrir(conteudo)
    inf = unico(raiz, "infCte")
    ide = filho(inf, "ide")
    mod = texto(ide, "mod")
    if mod != "57":
        raise XMLFiscalErro(f"Modelo incompatível para CT-e 57: {mod or 'ausente'}")
    versao = inf.get("versao")
    obj = resultado_base("57", "cte", versao, conteudo)
    campos, prov = obj["campos"], obj["proveniencia"]
    base = "//CTe/infCte"
    def g(nome, no, path, origem):
        return guardar(prov, nome, no, path, base + origem)
    def gd(nome, no, path, origem):
        return guardar_decimal(prov, nome, no, path, base + origem)
    for campo, caminho in (
        ("numero", "nCT"), ("serie", "serie"), ("emissao", "dhEmi"),
        ("natureza_operacao", "natOp"), ("tipo_cte", "tpCTe"),
        ("ambiente", "tpAmb"), ("modal", "modal"), ("servico", "tpServ"),
        ("municipio_inicio", "xMunIni"), ("uf_inicio", "UFIni"),
        ("municipio_fim", "xMunFim"), ("uf_fim", "UFFim"),
        ("uf_codigo", "cUF"),
    ):
        campos[campo] = g(campo, ide, caminho, "/ide")
    for nome, tag in (
        ("emitente", "emit"), ("remetente", "rem"), ("destinatario", "dest"),
        ("expedidor", "exped"), ("recebedor", "receb"), ("tomador", "toma3")):
        bloco = filho(inf, tag)
        dados = {k: g(nome + "." + k, bloco, path, "/" + tag)
                 for k, path in (("cnpj", "CNPJ"), ("cpf", "CPF"), ("nome", "xNome"), ("ie", "IE"))}
        if nome == "tomador":
            tom = filho(inf, "ide/toma3") or filho(inf, "ide/toma4")
            dados["codigo_tomador"] = texto(tom, "toma")
            if not dados["cnpj"]:
                dados["cnpj"] = texto(tom, "CNPJ")
            if not dados["nome"]:
                dados["nome"] = texto(tom, "xNome")
        campos[nome] = dados
    prest = filho(inf, "vPrest")
    campos["valor_total"] = gd("valor_total", prest, "vTPrest", "/vPrest")
    campos["valor_receber"] = gd("valor_receber", prest, "vRec", "/vPrest")
    campos["componentes_valor"] = [
        {"nome": texto(c, "xNome"), "valor": decimal(c, "vComp")}
        for c in filhos(prest, "Comp")]
    imp = filho(inf, "imp")
    campos["tributos"] = {}
    for grupo in filhos(imp, "ICMS"):
        for variante in grupo:
            campos["tributos"][local(variante.tag)] = {
                local(e.tag): (e.text or "").strip() for e in variante if e.text is not None}
    campos["tributos"]["vTotTrib"] = texto(imp, "vTotTrib")
    carga = filho(inf, "infCTeNorm/infCarga")
    campos["carga"] = {
        "valor": decimal(carga, "vCarga"), "produto_predominante": texto(carga, "proPred"),
        "outras_caracteristicas": texto(carga, "xOutCat"),
        "medidas": [{"codigo": texto(e, "cUnid"), "tipo": texto(e, "tpMed"),
                     "quantidade": decimal(e, "qCarga")} for e in filhos(carga, "infQ")],
    }
    info = filho(inf, "infCTeNorm/infDoc")
    for tipo, nome in (("nfe", "infNFe"), ("nf", "infNF"), ("outros", "infOutros")):
        for e in filhos(info, nome):
            ref = {local(c.tag): (c.text or "").strip() for c in e if c.text is not None}
            obj["referencias"].append({"tipo": tipo, **ref})
    multimodal = filho(inf, "infCTeNorm/infModal")
    campos["modal_rodoviario"] = {"rntrc": texto(multimodal, "rodo/RNTRC")}
    campos["informacoes_complementares"] = texto(inf, "compl/xObs")
    chave = identificador(inf, "CTe")
    campos["chave_acesso"] = chave
    campos["status_chave"] = chave_status(chave, "57")
    if campos["status_chave"] != "valida":
        obj["avisos"].append("Chave de acesso: " + campos["status_chave"])
    obj["protocolo"] = protocolo(raiz, "protCTe")
    if not versao:
        obj["avisos"].append("Versão do leiaute não informada em infCte")
    if not campos["valor_total"]:
        obj["avisos"].append("Valor da prestação vTPrest ausente")
    return obj
