"""Leitura da NFS-e, extração de contratos e regras de conciliação."""
from app import conciliacao, fiscal

CNPJ_A = "87000001100178"   # dígitos verificadores válidos (gerador sintético)
NOTA_NACIONAL = """<?xml version="1.0" encoding="UTF-8"?>
<NFSe xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">
 <infNFSe Id="NFS26116068700000110017800000000000300000608">
  <nNFSe>30000</nNFSe><dhProc>2026-08-01T09:00:00-03:00</dhProc>
  <emit><CNPJ>87000001100178</CNPJ><xNome>Limpeza Brilho ME</xNome></emit>
  <valores><vLiq>4000.00</vLiq></valores>
  <DPS versao="1.00"><infDPS Id="DPS1">
   <dhEmi>2026-08-01T08:00:00-03:00</dhEmi><dCompet>2026-08-01</dCompet>
   <prest><CNPJ>87000001100178</CNPJ></prest>
   <toma><CNPJ>87000999199999</CNPJ><xNome>Cliente</xNome></toma>
   <serv><cServ><cTribNac>070101</cTribNac><xDescServ>Limpeza e conservação da sede</xDescServ></cServ></serv>
   <valores><vServPrest><vServ>4000.00</vServ></vServPrest></valores>
  </infDPS></DPS>
 </infNFSe>
</NFSe>""".encode()


def test_cnpj_do_gerador_e_valido():
    assert fiscal.cnpj_valido(CNPJ_A)
    assert not fiscal.cnpj_valido("87000001100179")


def test_le_nfse_nacional():
    n = fiscal.ler_nfse_xml(NOTA_NACIONAL)
    assert n["formato"] == "NFS-e nacional"
    assert n["numero"] == "30000"
    assert n["cnpj_prestador"] == CNPJ_A
    assert n["cnpj_tomador"] == "87000999199999"
    assert n["nome_prestador"] == "Limpeza Brilho ME"
    assert n["valor"] == 4000.0 and n["valor_liquido"] == 4000.0
    assert n["data_emissao"] == "2026-08-01" and n["competencia"] == "2026-08"
    assert n["codigo_servico"] == "070101"
    assert n["chave"].startswith("2611606")


def test_le_xml_de_demonstracao_e_recusa_outro_xml():
    demo = b"""<NfseDemonstracao schema="x"><numero>31</numero><data_emissao>2026-09-30</data_emissao>
      <competencia>2026-09</competencia><prestador_cnpj>87.000.001/1001-78</prestador_cnpj>
      <tomador_cnpj>87.000.999/1999-99</tomador_cnpj><descricao_servico>Jardinagem</descricao_servico>
      <valor_servico>4350.00</valor_servico></NfseDemonstracao>"""
    n = fiscal.ler_nfse_xml(demo)
    assert n["formato"] == "XML de demonstração" and n["valor"] == 4350.0 and n["cnpj_prestador"] == CNPJ_A
    try:
        fiscal.ler_nfse_xml(b"<pedido><item>1</item></pedido>")
        assert False, "deveria recusar"
    except ValueError:
        pass


def test_xml_nacional_gerado_e_lido_de_volta():
    inv = {"numero": "30101", "data_emissao": "2026-08-31", "competencia": "2026-08",
           "prestador_cnpj": "87.000.001/1001-78", "tomador_cnpj": "87.000.999/1999-99",
           "descricao_servico": "Suporte técnico", "valor_servico": "4700.00"}
    n = fiscal.ler_nfse_xml(fiscal.nfse_nacional_xml(inv, "TI Express EPP"))
    assert (n["numero"], n["valor"], n["data_emissao"], n["nome_prestador"]) == ("30101", 4700.0, "2026-08-31", "TI Express EPP")


def test_extrai_contrato_aditivo_e_nota_do_texto():
    contrato = """CONTRATO DE PRESTACAO DE SERVICOS
Instrumento: CTR-001
Contratada: Limpeza Brilho ME
CNPJ contratada: 87.000.001/1001-78
CNPJ contratante: 87.000.999/1999-99
Objeto: Limpeza e conservação
Valor mensal: R$ 4.000,00
Vigencia: 01/01/2026 a 31/12/2026"""
    c = fiscal.extrair_local(fiscal.TIPO_CONTRATO, contrato)
    assert c["numero"] == "CTR-001" and c["cnpj_prestador"] == CNPJ_A and c["valor_mensal"] == 4000.0
    assert (c["vigencia_inicio"], c["vigencia_fim"]) == ("2026-01-01", "2026-12-31")
    assert c["objeto"] == "Limpeza e conservação" and c["nome_prestador"] == "Limpeza Brilho ME"
    a = fiscal.extrair_local(fiscal.TIPO_ADITIVO, "Aditivo: ADT-001\nContrato: CTR-001\nFornecedor: 87.000.001/1001-78\n"
                                                  "Acrescimo mensal: R$ 2.500,00\nVigencia do aditivo: 2026-08-01 ate 2026-12-31")
    assert a == {"numero": "ADT-001", "contrato_ref": "CTR-001", "cnpj_prestador": CNPJ_A, "valor_adicional": 2500.0,
                 "vigencia_inicio": "2026-08-01", "vigencia_fim": "2026-12-31"}
    n = fiscal.extrair_local(fiscal.TIPO_NOTA, "Numero: 30000\nPrestador: Limpeza Brilho ME\nCNPJ prestador: 87.000.001/1001-78\n"
                                               "Data emissao: 2026-08-01\nValor do servico: R$ 6.500,00\nContrato referenciado: nao informado")
    assert n["numero"] == "30000" and n["valor"] == 6500.0 and "contrato_ref" not in n


def _contrato(**k):
    c = {"id": 1, "numero": "CTR-001", "cnpj_prestador": CNPJ_A, "cnpj_tomador": "87000999199999",
         "objeto": "Limpeza e conservação", "valor_mensal": 4000.0, "vigencia_inicio": "2026-01-01", "vigencia_fim": "2026-12-31"}
    c.update(k)
    return c


def _nota(**k):
    n = {"id": 10, "numero": "30000", "cnpj_prestador": CNPJ_A, "cnpj_tomador": "87000999199999", "nome_prestador": "Limpeza Brilho ME",
         "data_emissao": "2026-08-01", "valor": 4000.0, "descricao": "Limpeza e conservação", "contrato_ref": None}
    n.update(k)
    return n


def _regras(nota, contratos=None, aditivos=(), notas=None, tol=0):
    achados, _, obs = conciliacao.avaliar_nota(nota, [_contrato()] if contratos is None else contratos, list(aditivos),
                                               notas or [nota], tol)
    return {a[0] for a in achados}, obs


def test_nota_certa_nao_gera_alerta():
    assert _regras(_nota()) == (set(), None)


def test_regras_basicas():
    assert _regras(_nota(valor=6500.0))[0] == {"VALOR_DIVERGENTE"}
    assert _regras(_nota(valor=4100.0), tol=5)[0] == set()
    assert _regras(_nota(data_emissao="2027-02-12"))[0] == {"FORA_VIGENCIA"}
    assert _regras(_nota(descricao="Consultoria financeira nao contratada"))[0] == {"SERVICO_DIVERGENTE"}
    assert _regras(_nota(), contratos=[])[0] == {"SEM_CONTRATO"}
    assert _regras(_nota(cnpj_tomador="11222333000181"))[0] == {"TOMADOR_DIVERGENTE"}


def test_aditivo_vigente_justifica_e_vencido_nao():
    vigente = {"numero": "ADT-001", "contrato_ref": "CTR-001", "cnpj_prestador": CNPJ_A, "valor_adicional": 2500.0,
               "vigencia_inicio": "2026-08-01", "vigencia_fim": "2026-12-31"}
    regras, obs = _regras(_nota(valor=6500.0), aditivos=[vigente])
    assert regras == set() and "ADT-001" in obs
    vencido = dict(vigente, vigencia_inicio="2026-02-01", vigencia_fim="2026-03-31")
    achados, _, _ = conciliacao.avaliar_nota(_nota(valor=6500.0), [_contrato()], [vencido], [], 0)
    assert achados[0][0] == "VALOR_DIVERGENTE" and "não estava vigente" in achados[0][1]


def test_duplicada_marca_so_a_segunda():
    a = _nota(id=1, data_emissao="2026-08-01")
    b = _nota(id=2, data_emissao="2026-08-31")
    assert _regras(a, notas=[a, b])[0] == set()
    assert _regras(b, notas=[a, b])[0] == {"NOTA_DUPLICADA"}


def test_le_contrato_digitalizado_com_palavras_coladas():
    ocr = ("CONTRATODEPRESTACAODESERVICOS\nInstrumento:CTR-001\nContratada:Azevedo-El\n"
           "CNPJcontratada:87.000.001/1001-78\nCNPJcontratante:87.000.999/1999-99\n"
           "Valormensal: R$ 4.000,00\nVigencia:01/01/2026a 31/12/2026")
    c = fiscal.extrair_local(fiscal.TIPO_CONTRATO, ocr)
    assert c["valor_mensal"] == 4000.0 and c["cnpj_tomador"] == "87000999199999"
    assert (c["vigencia_inicio"], c["vigencia_fim"]) == ("2026-01-01", "2026-12-31")
    # Só uma data legível: não inventa vigência (evita alarme falso de "fora da vigência").
    assert "vigencia_inicio" not in fiscal.extrair_local(fiscal.TIPO_CONTRATO, "Instrumento: CTR-9\nVigencia: 31/12/2026")


def test_notas_diferentes_com_mesmo_numero_tem_chaves_diferentes():
    base = {"numero": "30500", "competencia": "2026-08", "prestador_cnpj": "87.000.001/1001-78",
            "tomador_cnpj": "87.000.999/1999-99", "descricao_servico": "Jardinagem", "valor_servico": "5000.00"}
    a = fiscal.ler_nfse_xml(fiscal.nfse_nacional_xml(dict(base, data_emissao="2026-08-01", invoice_id="NF-006-01"), "X"))
    b = fiscal.ler_nfse_xml(fiscal.nfse_nacional_xml(dict(base, data_emissao="2026-08-31", invoice_id="NF-006-02"), "X"))
    assert len(a["chave"]) == 50 and a["chave"] != b["chave"]


def test_servico_com_palavras_coladas_pelo_ocr_nao_e_divergencia():
    c = _contrato(objeto="Servicosderecepcao")
    assert _regras(_nota(descricao="Serviços de recepção"), contratos=[c])[0] == set()
