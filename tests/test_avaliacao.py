from app import avaliacao

GABARITO = {
    "batch_total_pages": 5,
    "boundary_start_pages": [1, 3, 5],
    "documents": [
        {"document_id": "CTR-001", "type": "contrato", "batch_start_page": 1, "batch_end_page": 2},
        {"document_id": "NF-001", "type": "nota_fiscal_servico", "batch_start_page": 3, "batch_end_page": 4},
        {"document_id": "ADT-001", "type": "aditivo_contratual", "batch_start_page": 5, "batch_end_page": 5},
    ],
    "page_map": [
        {"batch_page": 1, "type": "contrato"}, {"batch_page": 2, "type": "contrato"},
        {"batch_page": 3, "type": "nota_fiscal_servico"}, {"batch_page": 4, "type": "nota_fiscal_servico"},
        {"batch_page": 5, "type": "aditivo_contratual"},
    ],
}


def doc(i, f, tipo, status="confirmado"):
    return {"pag_ini": i, "pag_fim": f, "tipo": tipo, "status": status, "decisao": None}


def test_tudo_certo_da_100():
    docs = [doc(1, 2, "Contrato de prestação de serviços"), doc(3, 4, "Nota fiscal de serviço"),
            doc(5, 5, "Aditivo contratual")]
    r = avaliacao.medir(GABARITO, docs, [])
    assert r["fronteira_f1"] == 100.0
    assert r["tipo_correto"] == 100.0
    assert r["total_erros"] == 0


def test_documentos_grudados_e_tipo_errado_sao_contados():
    docs = [doc(1, 4, "Contrato de prestação de serviços"), doc(5, 5, "Nota fiscal de serviço", "revisao")]
    r = avaliacao.medir(GABARITO, docs, [])
    assert r["fronteira_cobertura"] == 66.7       # não achou o início da página 3
    assert r["tipo_correto"] == 0.0
    assert r["enviados_revisao"] == 1
    assert r["total_erros"] == 3


def test_gerador_do_projeto_produz_gabarito(tmp_path, monkeypatch):
    monkeypatch.setattr(avaliacao, "DADOS", tmp_path)
    pasta = avaliacao.gerar_lote(fornecedores=3, notas=3, digitalizar=False, semente=1)
    assert (pasta / "lotes" / "lote_misturado.pdf").exists()
    assert (pasta / "ground_truth.json").exists()
