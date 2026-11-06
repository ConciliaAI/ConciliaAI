from app import analise, seed


def _tipos(nomes=None):
    out = []
    for nome, (tit, pal) in seed.BASE_TIPOS.items():
        out.append({"nome": nome, "titulos": tit, "palavras": pal})
    return out


def test_titulo_no_topo_inicia_documento_com_confianca_alta():
    texto = "ATESTADO DE SAÚDE OCUPACIONAL - ASO\nNome do colaborador: Marcos Silva\nResultado: APTO\nExame admissional"
    r = analise.analisar_local(texto, _tipos(), None, [])
    assert r["tipo"] == "ASO"
    assert r["inicio"] is True
    assert r["conf"] >= 95
    assert r["pessoa"] == "Marcos Silva"


def test_numeracao_continua_o_documento_anterior():
    anterior = {"tipo": "Ficha de registro", "pessoa": "Ana", "cpf": None}
    texto = "Dependentes: não possui\nAssinatura do empregado\nPágina 2 de 2"
    r = analise.analisar_local(texto, _tipos(), anterior, [])
    assert r["inicio"] is False
    assert r["tipo"] == "Ficha de registro"


def test_cpf_diferente_comeca_outro_documento():
    anterior = {"tipo": "Holerite", "pessoa": "Ana", "cpf": "111.222.333-44"}
    texto = "Competência 10/2026\nCPF: 999.888.777-66\nsalario base vencimentos descontos liquido a receber" * 2
    r = analise.analisar_local(texto, _tipos(), anterior, [])
    assert r["inicio"] is True


def test_pagina_sem_texto_util_vai_para_baixa_confianca():
    r = analise.analisar_local("xx yy", _tipos(), None, [])
    assert r["tipo"] == "Não identificado"
    assert r["conf"] < 75


def test_limpeza_do_ocr_separa_nomes_colados():
    b = analise.extrair_basico("Nome-do colaborador:.Ana Beatriz Rocha\nEmpresa:Servicos Litoral ME.CNPJ :12.345.678/0001-90")
    assert b["pessoa"] == "Ana Beatriz Rocha"
    assert b["empresa"] == "Servicos Litoral ME"
