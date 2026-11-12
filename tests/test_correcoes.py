"""Testes das correções da revisão de bugs (dados protegidos, login, ZIP, conferência, juntar documentos)."""
import csv
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import conciliacao, db, ocr, pipeline
from app.main import _CsvSeguro, _destacar, app
from tests.test_api import entrar, esperar, lote_pdf, nota_xml

WS = "marazul"


@pytest.fixture(scope="module")
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def envio(cliente):
    """Lote com contrato (com CPF no texto) e nota em PDF, enviado num cliente só destes testes."""
    entrar(cliente, "operador")
    r = cliente.post(f"/api/ws/{WS}/envios", files=[("arquivos", ("lote-correcoes.pdf", lote_pdf(), "application/pdf"))])
    assert r.status_code == 200, r.text
    e = esperar(cliente, r.json()["id"])
    contrato = next(d for d in e["docs"] if d["tipo"].startswith("Contrato"))
    nota = next(d for d in e["docs"] if d["tipo"].startswith("Nota"))
    pagina = next(p for p in e["paginas"] if p["n"] == contrato["pag_ini"])
    return {"contrato": contrato, "nota": nota, "pagina": pagina}


def test_imagem_sem_mascara_exige_revisor_e_motivo(cliente, envio):
    url = f"/api/paginas/{envio['pagina']['id']}/imagem?revelar=1"
    entrar(cliente, "operador")
    assert cliente.get(url).status_code == 403  # operador nunca vê sem máscara
    entrar(cliente, "revisor")
    assert cliente.get(url).status_code == 403  # revisor, mas sem ter registrado o motivo
    r = cliente.post(f"/api/docs/{envio['contrato']['id']}/revelar", json={"motivo": "Conferir assinatura do contrato"})
    assert r.status_code == 200, r.text
    assert cliente.get(url).status_code == 200
    assert cliente.get(f"/api/paginas/{envio['pagina']['id']}/imagem").status_code == 200  # com máscara: livre


def test_busca_mascara_cpf_mesmo_com_termo_no_meio(cliente, envio):
    entrar(cliente, "operador")
    r = cliente.get(f"/api/ws/{WS}/busca", params={"q": "654"}).json()
    assert r, "a busca devia achar o contrato"
    assert all("321.654.987-00" not in x["trecho"] and "654.987" not in x["trecho"] for x in r)


def test_destaque_da_busca():
    assert _destacar("Limpeza e conservação predial", ["conserv"]) == "Limpeza e [[conservação]] predial"
    assert _destacar("⟦CPF protegido⟧", ["321"]) == "⟦CPF protegido⟧"


def test_csv_neutraliza_formulas():
    buf = io.StringIO()
    _CsvSeguro(csv.writer(buf, delimiter=";")).writerow(['=HYPERLINK("http://x";"y")', "+1", "@SOMA", "normal", 10])
    linha = next(csv.reader(io.StringIO(buf.getvalue()), delimiter=";"))
    assert linha == ['\'=HYPERLINK("http://x";"y")', "'+1", "'@SOMA", "normal", "10"]


def test_login_bloqueia_depois_de_muitas_tentativas(cliente):
    cliente.cookies.clear()
    assert cliente.post("/api/login", json={"usuario": ["admin"], "senha": "x"}).status_code == 400
    for _ in range(5):
        assert cliente.post("/api/login", json={"usuario": "ninguem", "senha": "errada"}).status_code == 401
    assert cliente.post("/api/login", json={"usuario": "ninguem", "senha": "errada"}).status_code == 429


def test_sair_invalida_o_cookie(cliente):
    entrar(cliente, "operador")
    token = cliente.cookies.get("concilia_sessao")
    assert cliente.get(f"/api/ws/{WS}/contagens").status_code == 200
    cliente.post("/api/sair")
    cliente.cookies.clear()
    cliente.cookies.set("concilia_sessao", token)  # alguém que copiou o cookie antes do "Sair"
    assert cliente.get(f"/api/ws/{WS}/contagens").status_code == 401


def test_zip_corrompido_e_recusado_e_pode_ser_reenviado(cliente):
    entrar(cliente, "operador")
    ruim = b"isto nao e um zip"
    for _ in range(2):  # a segunda vez não pode cair em "já foi enviado"
        r = cliente.post(f"/api/ws/{WS}/envios", files=[("arquivos", ("lote.zip", ruim, "application/zip"))])
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "recusado"
        assert "ZIP ignorado" in r.json()["erro"]


def test_zip_grande_demais_ao_descompactar(tmp_path, monkeypatch):
    caminho = tmp_path / "bomba.zip"
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("grande.pdf", b"0" * 5000)
    monkeypatch.setattr(pipeline, "MAX_BYTES", 1000)
    with pytest.raises(ValueError):
        pipeline._abrir_zip(caminho, tmp_path, 0)


def test_conferencia_remove_divergencia_duplicada(cliente):
    entrar(cliente, "operador")
    r = cliente.post(f"/api/ws/{WS}/envios", files=[("arquivos", ("sem-contrato.xml", nota_xml("4321", "87.000.700/1700-34", "300.00"), "application/xml"))])
    assert r.json()["status"] == "concluido", r.text
    nota = next(n for n in cliente.get(f"/api/ws/{WS}/notas").json() if n["numero"] == "4321")
    d = db.q("SELECT * FROM divergencias WHERE nota_id=?", (nota["id"],), um=True)
    db.x("""INSERT INTO divergencias(ws, nota_id, regra, severidade, mensagem, status, criado_em)
            VALUES(?,?,?,?,?, 'aberta', ?)""", (WS, nota["id"], d["regra"], d["severidade"], d["mensagem"], db.agora()))
    conciliacao.conciliar(WS)
    assert len(db.q("SELECT id FROM divergencias WHERE nota_id=?", (nota["id"],))) == 1


def test_juntar_tira_a_nota_lida_do_documento_juntado(cliente, envio):
    entrar(cliente, "revisor")
    notas = [n["numero"] for n in cliente.get(f"/api/ws/{WS}/notas").json()]
    assert "501" in notas
    r = cliente.post(f"/api/docs/{envio['nota']['id']}/decisao", json={"acao": "juntar"})
    assert r.status_code == 200, r.text
    assert "501" not in [n["numero"] for n in cliente.get(f"/api/ws/{WS}/notas").json()]


def test_pagina_que_sempre_falha_e_pulada(cliente, monkeypatch):
    original = ocr.renderizar

    def renderizar(arquivo, indice, *args, **kwargs):
        if "quebrado" in str(arquivo) and indice == 0:
            raise OSError("página corrompida")
        return original(arquivo, indice, *args, **kwargs)

    monkeypatch.setattr(ocr, "renderizar", renderizar)
    entrar(cliente, "operador")
    r = cliente.post(f"/api/ws/{WS}/envios", files=[("arquivos", ("quebrado.pdf", lote_pdf() + b"% outra copia", "application/pdf"))])
    e = esperar(cliente, r.json()["id"], limite=90)  # 3 tentativas com retomada automática a cada 4 s
    assert e["envio"]["status"] == "concluido"
    assert next(p for p in e["paginas"] if p["n"] == 1)["status"] == "erro"
    assert any("pulada" in ev["texto"] for ev in e["eventos"])


def test_cancelar_envio_e_resultado_na_lista(cliente, envio):
    entrar(cliente, "operador")
    eid = db.x("INSERT INTO envios(ws, nome, origem, criado_em, status, total, feitas) VALUES(?,?,?,?, 'pausado', 10, 3)",
               (WS, "pausado.pdf", "teste", db.agora()))
    r = cliente.post(f"/api/envios/{eid}/cancelar")
    assert r.status_code == 200, r.text
    assert db.q("SELECT status FROM envios WHERE id=?", (eid,), um=True)["status"] == "cancelado"
    assert cliente.post(f"/api/envios/{eid}/cancelar").status_code == 400  # já terminou
    lista = {e["id"]: e for e in cliente.get(f"/api/ws/{WS}/envios").json()}
    assert lista[envio["contrato"]["envio_id"]]["documentos"] >= 1
    assert "duvidas" in lista[eid]
