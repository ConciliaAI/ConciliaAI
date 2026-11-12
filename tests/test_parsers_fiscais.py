"""Testes dos parsers DF-e 55/65/57 e do fluxo HTTP de importação.

Os documentos são amostras sintéticas; não representam autorização SEFAZ nem
substituem a suíte oficial de conformidade por versão de XSD.
"""
import pytest

from app.fiscal_xml_comum import XMLFiscalErro
from app.roteador_fiscal import detectar_modelo, interpretar
from app.parser_nfe import ler_nfe
from app.parser_nfce import ler_nfce
from app.parser_cte import ler_cte


def chave(modelo):
    # 43 primeiros dígitos no padrão cUF(2)+AAMM(4)+CNPJ(14)+mod(2)+
    # série(3)+número(9)+tpEmis(1)+cNF(8).
    p = "26" + "2611" + "87000001100178" + modelo + "001" + "000000123" + "1" + "12345678"
    assert len(p) == 43
    dv = (11 - sum(int(c) * (i % 8 + 2) for i, c in enumerate(p[::-1])) % 11) % 11
    if dv >= 10:
        dv = 0
    return p + str(dv)


def xml_nfe(modelo="55", proc=True):
    c = chave(modelo)
    corpo = f"""<NFe xmlns="http://www.portalfiscal.inf.br/nfe">
    <infNFe versao="4.00" Id="NFe{c}">
      <ide><cUF>26</cUF><natOp>VENDA</natOp><mod>{modelo}</mod><serie>1</serie>
        <nNF>123</nNF><dhEmi>2026-11-12T10:00:00-03:00</dhEmi><tpNF>1</tpNF><tpAmb>2</tpAmb>
      </ide>
      <emit><CNPJ>87000001100178</CNPJ><xNome>COMERCIO TESTE</xNome>
        <enderEmit><xLgr>Rua A</xLgr><nro>12</nro><xMun>Garanhuns</xMun><UF>PE</UF></enderEmit>
      </emit>
      <dest><CPF>12345678909</CPF><xNome>CONSUMIDOR</xNome></dest>
      <det nItem="1"><prod><cProd>P01</cProd><xProd>Produto de teste</xProd><NCM>12345678</NCM>
       <CFOP>5102</CFOP><uCom>UN</uCom><qCom>2.0000</qCom><vUnCom>10.00</vUnCom>
       <vProd>20.00</vProd></prod><imposto><ICMS><ICMS00><CST>00</CST>
       <vBC>20.00</vBC><vICMS>3.60</vICMS></ICMS00></ICMS></imposto></det>
      <total><ICMSTot><vProd>20.00</vProd><vNF>20.00</vNF><vICMS>3.60</vICMS></ICMSTot></total>
      <transp><modFrete>9</modFrete></transp>
      <pag><detPag><tPag>01</tPag><vPag>20.00</vPag></detPag><vTroco>0.00</vTroco></pag>
    </infNFe>
    <infNFeSupl><qrCode>https://sefaz.exemplo/qr</qrCode></infNFeSupl>
    </NFe>"""
    if not proc:
        return corpo.encode()
    return f"""<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
        {corpo}<protNFe><infProt><chNFe>{c}</chNFe><cStat>100</cStat>
        <nProt>123456789012345</nProt></infProt></protNFe></nfeProc>""".encode()


def xml_cte():
    c = chave("57")
    return f"""<cteProc xmlns="http://www.portalfiscal.inf.br/cte" versao="4.00">
    <CTe><infCte versao="4.00" Id="CTe{c}">
     <ide><mod>57</mod><serie>1</serie><nCT>123</nCT><dhEmi>2026-11-12T10:00:00-03:00</dhEmi>
     <xMunIni>Garanhuns</xMunIni><UFIni>PE</UFIni><xMunFim>Recife</xMunFim><UFFim>PE</UFFim>
     <modal>01</modal><tpAmb>2</tpAmb></ide>
     <emit><CNPJ>87000001100178</CNPJ><xNome>TRANSPORTES TESTE</xNome></emit>
     <rem><CNPJ>12345678000190</CNPJ><xNome>REMETENTE</xNome></rem>
     <dest><CNPJ>11222333000181</CNPJ><xNome>DESTINATARIO</xNome></dest>
     <vPrest><vTPrest>100.00</vTPrest><vRec>95.00</vRec>
       <Comp><xNome>Frete</xNome><vComp>100.00</vComp></Comp></vPrest>
     <imp><ICMS><ICMS00><CST>00</CST><vICMS>12.00</vICMS></ICMS00></ICMS></imp>
     <infCTeNorm><infCarga><vCarga>200.00</vCarga><proPred>Caixas</proPred>
       <infQ><cUnid>01</cUnid><tpMed>KG</tpMed><qCarga>30.0000</qCarga></infQ></infCarga>
       <infDoc><infNFe><chave>{chave("55")}</chave></infNFe></infDoc>
       <infModal><rodo><RNTRC>12345678</RNTRC></rodo></infModal>
     </infCTeNorm>
    </infCte></CTe>
    <protCTe><infProt><cStat>100</cStat><nProt>987654321</nProt></infProt></protCTe>
    </cteProc>""".encode()


@pytest.mark.parametrize("modelo,func,tipo", [
    ("55", ler_nfe, "nfe"), ("65", ler_nfce, "nfce")
])
def test_nf_modelo_itens_tributos_proveniencia(modelo, func, tipo):
    xml = xml_nfe(modelo)
    r = func(xml)
    assert r["modelo"] == modelo and r["tipo"] == tipo and r["versao"] == "4.00"
    assert r["campos"]["numero"] == "123"
    assert r["campos"]["valor_total"] == "20.00"
    assert r["itens"][0]["ncm"] == "12345678"
    assert r["itens"][0]["cfop"] == "5102"
    assert r["itens"][0]["impostos"]["ICMS"]["ICMS00"]["vICMS"] == "3.60"
    assert r["proveniencia"]["itens.1.ncm"]["caminho_xml"].endswith("/det[@nItem='1']/prod/NCM")
    assert r["campos"]["status_chave"] == "valida"
    assert r["protocolo"]["autorizado"] is True
    assert r["validacao"]["xsd"] == "nao_executada"


def test_nfe_nao_aceita_nfce_e_vice_versa():
    with pytest.raises(XMLFiscalErro):
        ler_nfe(xml_nfe("65"))
    with pytest.raises(XMLFiscalErro):
        ler_nfce(xml_nfe("55"))


def test_nfce_consumidor_pagamento_qrcode():
    r = interpretar(xml_nfe("65"))
    assert r["campos"]["consumidor_identificado"]
    assert r["campos"]["pagamentos"][0]["forma"] == "01"
    assert r["campos"]["troco"] == "0.00"
    assert "qr" in r["campos"]["qr_code"]


def test_cte_modal_referencia_tributo_partes():
    r = ler_cte(xml_cte())
    assert r["tipo"] == "cte"
    assert r["campos"]["modal_rodoviario"]["rntrc"] == "12345678"
    assert r["campos"]["remetente"]["nome"] == "REMETENTE"
    assert r["campos"]["valor_total"] == "100.00"
    assert r["campos"]["carga"]["medidas"][0]["quantidade"] == "30.0000"
    assert r["referencias"][0]["chave"] == chave("55")
    assert r["protocolo"]["autorizado"]
    assert r["campos"]["status_chave"] == "valida"


def test_xml_sem_protocolo_nao_e_autorizado():
    r = interpretar(xml_nfe("55", proc=False))
    assert not r["protocolo"]["autorizado"]
    assert r["validacao"]["autorizacao_online"] == "nao_consultada"


def test_protecao_xml_dtd_entidade_e_estrutura():
    with pytest.raises(XMLFiscalErro):
        interpretar(b'<!DOCTYPE nfe [<!ENTITY x "teste">]><NFe>&x;</NFe>')
    with pytest.raises(XMLFiscalErro):
        interpretar(b"<nfeProc><NFe></nfeProc>")
    with pytest.raises(XMLFiscalErro):
        interpretar(xml_nfe("55").replace(b"<mod>55</mod>", b"<mod>99</mod>"))


def test_nfse_continua_no_parser_existente():
    from app import fiscal
    dados = {"numero": "501", "prestador_cnpj": "87000001100178",
             "tomador_cnpj": "87000999199999", "data_emissao": "2026-10-05",
             "competencia": "2026-10", "descricao_servico": "Limpeza",
             "valor_servico": "500.00"}
    xml = fiscal.nfse_nacional_xml(dados, "Empresa teste")
    assert detectar_modelo(xml) == "nfse_ou_desconhecido"
    assert interpretar(xml) is None
    assert fiscal.ler_nfse_xml(xml)["numero"] == "501"


def test_importacao_xml_e_api_lista_e_detalhes():
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        login = c.post("/api/login", json={"usuario": "operador", "senha": "operador123"})
        assert login.status_code == 200
        arquivo = ("nfe_teste.xml", xml_nfe("55"), "application/xml")
        post = c.post("/api/ws/horizonte/envios", files=[("arquivos", arquivo)])
        assert post.status_code == 200, post.text
        envio = post.json()
        assert envio["status"] == "concluido", envio
        dados = c.get(f"/api/envios/{envio['id']}").json()
        assert dados["fiscais"] and dados["fiscais"][0]["modelo"] == "55"
        lista = c.get("/api/ws/horizonte/documentos-fiscais", params={"modelo": "55"})
        assert lista.status_code == 200
        df = next(d for d in lista.json() if d["envio_id"] == envio["id"])
        detalhe = c.get(f"/api/documentos-fiscais/{df['id']}")
        assert detalhe.status_code == 200
        assert detalhe.json()["campos"]["valor_total"] == "20.00"
        assert detalhe.json()["itens"][0]["codigo"] == "P01"


@pytest.mark.parametrize("modelo,nome,conteudo", [
    ("65", "nfce_teste.xml", xml_nfe("65")),
    ("57", "cte_teste.xml", xml_cte()),
])
def test_integracao_api_demais_modelos(modelo, nome, conteudo):
    from app.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        login = c.post("/api/login", json={"usuario": "operador", "senha": "operador123"})
        assert login.status_code == 200
        post = c.post("/api/ws/marazul/envios", files=[("arquivos", (nome, conteudo, "application/xml"))])
        assert post.status_code == 200, post.text
        envio = post.json()
        assert envio["status"] == "concluido", envio
        detalhe_envio = c.get(f"/api/envios/{envio['id']}").json()
        assert any(d["modelo"] == modelo for d in detalhe_envio["fiscais"])
        lista = c.get("/api/ws/marazul/documentos-fiscais", params={"modelo": modelo})
        assert lista.status_code == 200
        doc = next(d for d in lista.json() if d["envio_id"] == envio["id"])
        item = c.get(f"/api/documentos-fiscais/{doc['id']}").json()
        assert item["modelo"] == modelo
        assert item["protocolo"]["codigo"] == "100"


def test_xsd_nao_configurado_nao_simula_aprovacao(monkeypatch):
    from app.validador_xsd import validar_xsd
    monkeypatch.delenv("CONCILIA_XSD_DIR", raising=False)
    resultado = validar_xsd(xml_nfe("55"), "55", "4.00")
    assert resultado["xsd"] == "nao_executada"
