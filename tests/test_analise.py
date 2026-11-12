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


def _pags(*textos):
    return [{"n": i + 1, "texto": t} for i, t in enumerate(textos)]


def test_integridade_documento_inteiro():
    from app.pipeline import integridade
    assert integridade(_pags(*(f"Contrato\nSecao {k}\nPagina {k} de 3" for k in (1, 2, 3)))) == []


def test_integridade_pagina_repetida_e_faltando():
    from app.pipeline import integridade
    rep = integridade(_pags(*(f"Contrato secao {k}\nPagina {k} de 4" for k in (1, 2, 2, 3, 4))))
    assert any("Página repetida: a página 2 de 4" in p for p in rep)
    falta = integridade(_pags(*(f"Contrato secao {k}\nPagina {k} de 5" for k in (1, 2, 4, 5))))
    assert falta == ["Documento incompleto: falta a página 3 de 5"]
    # Página ilegível (sem numeração) no lugar da que falta: não acusa.
    assert integridade(_pags("Contrato\nPagina 1 de 3", "xx", "Contrato\nPagina 3 de 3")) == []


def test_integridade_mesma_folha_escaneada_duas_vezes():
    from app.pipeline import integridade
    folha = "NOTA FISCAL DE SERVICOS " + "Prestador Limpeza Brilho ME valor do servico 4.000,00 " * 6
    r = integridade(_pags("Contrato " * 30, folha, folha))
    assert any("escaneada duas vezes" in p for p in r)
