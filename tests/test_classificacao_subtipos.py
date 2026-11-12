"""Identificação complementar e integração com o pipeline em banco temporário."""
import json
import pytest
from app import db, pipeline
from app.classificacao_subtipos import identificar_subtipo, SUBTIPOS

@pytest.mark.parametrize("texto, esperado", [
    ("NFS-e Nota Fiscal de Serviços", "nfse"),
    ("DANFE Documento Auxiliar da Nota Fiscal Eletrônica", "danfe"),
    ("DANFCE Nota Fiscal de Consumidor Eletrônica", "nfce"),
    ("DACTE Conhecimento de Transporte Eletrônico", "cte"),
    ("Termo aditivo ao contrato de prestação de serviços", "aditivo"),
    ("Termo de distrato contratual", "distrato"),
    ("Contrato de prestação de serviços", "contrato"),
    ("Boleto bancário linha digitável", "boleto"),
    ("Comprovante de pagamento Pix", "comprovante_pagamento"),
    ("Recibo de pagamento", "recibo"),
])
def test_subtipos(texto, esperado):
    r = identificar_subtipo(texto)
    assert r["subtipo"] == esperado
    assert r["evidencias"]

def test_vazio_e_ambiguo():
    assert identificar_subtipo("")["revisao_necessaria"]
    r = identificar_subtipo("TERMO ADITIVO TERMO DE DISTRATO")
    assert r["revisao_necessaria"]
    assert r["alternativas"]

def _montar_doc(texto):
    eid = db.x("INSERT INTO envios(ws, nome, status) VALUES(?,?,?)",
               ("horizonte", "subtipo-teste", "concluido"))
    db.x("""INSERT INTO paginas(envio_id, n, texto, status) VALUES(?,?,?,'feita')""",
         (eid, 1, texto))
    did = db.x("""INSERT INTO docs(envio_id, ws, tipo, conf, pag_ini, pag_fim, status)
                  VALUES(?,?,?,?,?,?,?)""",
               (eid, "horizonte", "Não identificado", 80, 1, 1, "confirmado"))
    return did

def test_persistencia_apos_ocr_e_preservacao_manual():
    did = _montar_doc("DACTE Conhecimento de Transporte Eletrônico")
    r = pipeline.atualizar_subtipo(did)
    assert r["subtipo"] == "cte"
    doc = db.q("SELECT * FROM docs WHERE id=?", (did,), um=True)
    assert doc["subtipo"] == "cte"
    assert json.loads(doc["subtipo_evidencias"])
    db.x("UPDATE docs SET subtipo='boleto', subtipo_manual=1 WHERE id=?", (did,))
    assert pipeline.atualizar_subtipo(did) is None
    assert db.q("SELECT subtipo FROM docs WHERE id=?", (did,), um=True)["subtipo"] == "boleto"
    pipeline.atualizar_subtipo(did, forcar=True)
    assert db.q("SELECT subtipo FROM docs WHERE id=?", (did,), um=True)["subtipo"] == "cte"

def test_endpoint_revisao_subtipo():
    from fastapi.testclient import TestClient
    from app.main import app
    did = _montar_doc("Comprovante de pagamento")
    pipeline.atualizar_subtipo(did)
    with TestClient(app) as c:
        login = c.post("/api/login", json={"usuario": "revisor", "senha": "revisor123"})
        assert login.status_code == 200
        r = c.post(f"/api/docs/{did}/decisao", json={"acao": "corrigir_subtipo", "subtipo": "recibo"})
        assert r.status_code == 200, r.text
        d = c.get(f"/api/docs/{did}")
        assert d.status_code == 200
        assert d.json()["subtipo"] == "recibo"
        assert d.json()["subtipo_manual"] is True
        assert c.post(f"/api/docs/{did}/decisao", json={"acao":"corrigir_subtipo", "subtipo":"arbitrario"}).status_code == 400
