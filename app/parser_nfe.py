"""Parser específico para NF-e modelo 55.

Extrai dados dos grupos ide, emit, dest, det/prod/imposto, total, transp,
pag, cobr, infAdic e protocolo, mantendo trilha dos campos principais.
"""
from .fiscal_xml_comum import (
    XMLFiscalErro, abrir, unico, filho, filhos, texto, decimal,
    guardar, guardar_decimal, protocolo, resultado_base, identificador, chave_status, local, serializar_no
)


def _grupos_tributos(imposto):
    # Preserva campos novos do leiaute (inclusive IBS/CBS e IS) sem
    # pressupor que os tributos tenham só dois níveis XML.
    return {local(grupo.tag): serializar_no(grupo) for grupo in imposto} if imposto is not None else {}


def _ler_nfe(conteudo: bytes, esperado: str):
    raiz = abrir(conteudo)
    inf = unico(raiz, "infNFe")
    ide = filho(inf, "ide")
    mod = texto(ide, "mod")
    if mod != esperado:
        raise XMLFiscalErro(f"Modelo incompatível: esperado {esperado}, encontrado {mod or 'ausente'}")
    versao = inf.get("versao")
    obj = resultado_base(esperado, "nfe" if esperado == "55" else "nfce", versao, conteudo)
    prov = obj["proveniencia"]
    campos = obj["campos"]
    base = "//NFe/infNFe"
    def g(nome, grupo, caminho, prefixo):
        return guardar(prov, nome, grupo, caminho, base + prefixo)
    def gd(nome, grupo, caminho, prefixo):
        return guardar_decimal(prov, nome, grupo, caminho, base + prefixo)
    for campo, caminho in (
        ("numero", "nNF"), ("serie", "serie"), ("emissao", "dhEmi"),
        ("saida_entrada", "dhSaiEnt"), ("natureza_operacao", "natOp"),
        ("tipo_operacao", "tpNF"), ("finalidade", "finNFe"),
        ("ambiente", "tpAmb"), ("uf_codigo", "cUF"), ("municipio_fato_gerador", "cMunFG"),
    ):
        campos[campo] = g(campo, ide, caminho, "/ide")
    for prefixo, tag in (("emitente", "emit"), ("destinatario", "dest")):
        bloco = filho(inf, tag)
        dados = {}
        for campo, caminho in (("cnpj", "CNPJ"), ("cpf", "CPF"), ("nome", "xNome"),
                              ("fantasia", "xFant"), ("inscricao_estadual", "IE")):
            dados[campo] = g(prefixo + "." + campo, bloco, caminho, "/" + tag)
        endereco = filho(bloco, "enderEmit" if tag == "emit" else "enderDest")
        dados["endereco"] = {chave: texto(endereco, xml) for chave, xml in (
            ("logradouro", "xLgr"), ("numero", "nro"), ("bairro", "xBairro"),
            ("municipio", "xMun"), ("uf", "UF"), ("cep", "CEP"), ("pais", "xPais"))}
        campos[prefixo] = dados
    total = filho(inf, "total/ICMSTot")
    campos["totais"] = {
        campo: gd("totais." + campo, total, tag, "/total/ICMSTot")
        for campo, tag in (
            ("produtos", "vProd"), ("frete", "vFrete"), ("seguro", "vSeg"),
            ("desconto", "vDesc"), ("outros", "vOutro"), ("icms", "vICMS"),
            ("icms_st", "vST"), ("ipi", "vIPI"), ("pis", "vPIS"),
            ("cofins", "vCOFINS"), ("tributos_aproximados", "vTotTrib"),
            ("nota", "vNF"))}
    campos["totais_complementares"] = {
        local(e.tag): serializar_no(e) for e in filho(inf, "total")
        if local(e.tag) != "ICMSTot"
    } if filho(inf, "total") is not None else {}
    campos["valor_total"] = campos["totais"]["nota"]
    for det in filhos(inf, "det"):
        prod = filho(det, "prod")
        imposto = filho(det, "imposto")
        item = {
            "numero_item": det.get("nItem"),
            "codigo": texto(prod, "cProd"), "ean": texto(prod, "cEAN"),
            "descricao": texto(prod, "xProd"), "ncm": texto(prod, "NCM"),
            "cest": texto(prod, "CEST"), "cfop": texto(prod, "CFOP"),
            "unidade": texto(prod, "uCom"), "quantidade": decimal(prod, "qCom"),
            "valor_unitario": decimal(prod, "vUnCom"),
            "valor_produtos": decimal(prod, "vProd"),
            "desconto": decimal(prod, "vDesc"),
            "valor_frete": decimal(prod, "vFrete"),
            "impostos": _grupos_tributos(imposto),
            "informacoes_adicionais": texto(det, "infAdProd"),
        }
        n = det.get("nItem", str(len(obj["itens"]) + 1))
        for campo, xpath in (("descricao", "xProd"), ("ncm", "NCM"), ("cfop", "CFOP"),
                             ("quantidade", "qCom"), ("valor_produtos", "vProd")):
            if item[campo] is not None:
                prov[f"itens.{n}.{campo}"] = {
                    "caminho_xml": f"{base}/det[@nItem='{n}']/prod/{xpath}",
                    "valor_original": texto(prod, xpath),
                    "origem": "extraido", "metodo": "xml_deterministico"}
        obj["itens"].append(item)
    trans = filho(inf, "transp")
    transp = filho(trans, "transporta")
    campos["transporte"] = {
        "modalidade_frete": texto(trans, "modFrete"),
        "cnpj_transportador": texto(transp, "CNPJ"),
        "nome_transportador": texto(transp, "xNome"),
        "placa": texto(trans, "veicTransp/placa"),
        "volumes": [
            {"quantidade": texto(v, "qVol"), "especie": texto(v, "esp"),
             "peso_liquido": decimal(v, "pesoL"), "peso_bruto": decimal(v, "pesoB")}
            for v in filhos(trans, "vol")
        ],
    }
    campos["pagamentos"] = [
        {"forma": texto(det, "tPag"), "valor": decimal(det, "vPag")}
        for pag in filhos(inf, "pag") for det in filhos(pag, "detPag")
    ]
    cobr = filho(inf, "cobr")
    campos["cobranca"] = {
        "fatura": {"numero": texto(cobr, "fat/nFat"), "valor_original": decimal(cobr, "fat/vOrig"),
                   "valor_liquido": decimal(cobr, "fat/vLiq")},
        "duplicatas": [{"numero": texto(dup, "nDup"), "vencimento": texto(dup, "dVenc"),
                        "valor": decimal(dup, "vDup")} for dup in filhos(cobr, "dup")],
    }
    campos["informacoes_complementares"] = texto(inf, "infAdic/infCpl")
    for ref in filhos(filho(inf, "ide"), "NFref"):
        obj["referencias"].append(
            {local(e.tag): (e.text or "").strip() for e in ref if e.text is not None})
    chave = identificador(inf, "NFe")
    if not chave:
        prot = next((e for e in raiz.iter() if local(e.tag) == "protNFe"), None)
        chave = texto(filho(prot, "infProt"), "chNFe")
    campos["chave_acesso"] = chave
    campos["status_chave"] = chave_status(chave, esperado)
    if campos["status_chave"] != "valida":
        obj["avisos"].append("Chave de acesso: " + campos["status_chave"])
    obj["protocolo"] = protocolo(raiz, "protNFe")
    if not versao:
        obj["avisos"].append("Versão do leiaute não informada em infNFe")
    if not obj["itens"]:
        obj["avisos"].append("Nenhum item det encontrado")
    if not campos["valor_total"]:
        obj["avisos"].append("Valor total vNF ausente")
    return obj


def ler_nfe(conteudo: bytes):
    return _ler_nfe(conteudo, "55")
