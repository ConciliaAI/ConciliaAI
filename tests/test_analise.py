from app import analise, seed


def _tipos():
    return [{"nome": nome, "titulos": tit, "palavras": pal} for nome, (tit, pal) in seed.TIPOS.items()]


def test_titulo_no_topo_inicia_documento_com_confianca_alta():
    texto = ("NOTA FISCAL DE SERVIÇOS ELETRÔNICA - NFS-e\nPrestador: Limpeza Brilho ME\nTomador: Atlântica Facilities\n"
             "Data emissao: 01/08/2026\nValor do servico: R$ 4.000,00\nCompetencia: 08/2026")
    r = analise.analisar_local(texto, _tipos(), None, [])
    assert r["tipo"] == "Nota fiscal de serviço"
    assert r["inicio"] is True
    assert r["conf"] >= 95


def test_numeracao_continua_o_documento_anterior():
    anterior = {"tipo": "Contrato de prestação de serviços", "pessoa": None, "cpf": None}
    texto = "Cláusula sétima: foro da comarca\nAssinaturas das partes\nPágina 2 de 2"
    r = analise.analisar_local(texto, _tipos(), anterior, [])
    assert r["inicio"] is False
    assert r["tipo"] == "Contrato de prestação de serviços"


def test_tipo_diferente_comeca_outro_documento():
    anterior = {"tipo": "Contrato de prestação de serviços", "pessoa": None, "cpf": None}
    texto = "TERMO ADITIVO CONTRATUAL\nAditivo: ADT-001\nAcrescimo mensal: R$ 2.500,00\nVigencia do aditivo: 2026-08-01 ate 2026-12-31"
    r = analise.analisar_local(texto, _tipos(), anterior, [])
    assert r["inicio"] is True
    assert r["tipo"] == "Aditivo contratual"


def test_pagina_sem_texto_util_vai_para_baixa_confianca():
    r = analise.analisar_local("xx yy", _tipos(), None, [])
    assert r["tipo"] == "Não identificado"
    assert r["conf"] < 75


def test_limpeza_do_ocr_separa_nomes_colados():
    b = analise.extrair_basico("Contratada:.Limpeza Brilho ME.CNPJ :12.345.678/0001-90")
    assert b["empresa"] == "Limpeza Brilho ME"
