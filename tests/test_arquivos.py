"""Arquivos no Storage do Supabase (simulado em memória) e envios processados só por quem os recebeu."""
import time

import pytest
from fastapi.testclient import TestClient

from app import arquivos, config, db
from app.main import app
from tests.test_api import entrar, esperar, lote_pdf


class StorageFalso:
    """Imita as rotas do Storage usadas pela plataforma."""

    def __init__(self):
        self.objetos, self.buckets = {}, set()

    def __call__(self, metodo, caminho, **kw):
        class R:
            def __init__(self, status, conteudo=b"", texto=""):
                self.status_code, self.content, self.text = status, conteudo, texto
        if caminho.startswith("bucket"):
            if metodo == "GET":
                return R(200 if caminho.split("/")[-1] in self.buckets else 404)
            self.buckets.add(kw["json"]["id"])
            assert kw["json"]["public"] is False  # bucket sempre privado
            return R(200)
        _, bucket, *resto = caminho.split("/")
        chave = "/".join(resto)
        if metodo == "POST":
            self.objetos[chave] = kw["content"]
            return R(200)
        if metodo == "GET":
            return R(200, self.objetos[chave]) if chave in self.objetos else R(404)
        if metodo == "DELETE":
            for k in kw["json"]["prefixes"]:
                self.objetos.pop(k, None)
            return R(200)
        return R(405)


@pytest.fixture
def storage(monkeypatch):
    falso = StorageFalso()
    monkeypatch.setattr(config, "SUPABASE_URL", "https://exemplo.supabase.co")
    monkeypatch.setattr(config, "SUPABASE_CHAVE", "sb_secret_teste")
    monkeypatch.setattr(arquivos, "_requisicao", falso)
    arquivos._bucket_pronto.clear()
    return falso


def test_chave_vale_em_qualquer_computador():
    assert arquivos.chave(r"C:\Users\Ana\Concilia AI\dados\paginas\12_0001.png") == "paginas/12_0001.png"
    assert arquivos.chave("/home/ruan/concilia/dados/envios/7/000_lote.pdf") == "envios/7/000_lote.pdf"
    assert arquivos.chave("paginas/3_0002.png") == "paginas/3_0002.png"
    assert arquivos.chave(None) is None


def test_sem_configuracao_nada_vai_para_o_storage():
    assert not arquivos.ativo()


def test_paginas_vao_para_o_storage_e_voltam_em_outro_computador(storage):
    with TestClient(app) as c:
        entrar(c, "admin")
        r = c.post("/api/ws/atlantica/envios", files=[("arquivos", ("lote-storage.pdf", lote_pdf(), "application/pdf"))])
        assert r.status_code == 200, r.text
        e = esperar(c, r.json()["id"])
        arquivos.aguardar()
        assert config.STORAGE_BUCKET in storage.buckets
        assert any(k.startswith(f"envios/{e['envio']['id']}/") for k in storage.objetos)  # o original

        pagina = e["paginas"][0]
        img = db.q("SELECT img FROM paginas WHERE id=?", (pagina["id"],), um=True)["img"]
        assert img.startswith("paginas/")  # chave relativa no banco, não o caminho deste computador
        assert img in storage.objetos

        # "Outro computador": o arquivo não está no disco, então a imagem vem do Storage.
        (config.DADOS / img).unlink()
        for mini in (config.DADOS / "miniaturas").glob(f"{pagina['id']}_*.jpg"):
            mini.unlink()
        assert c.get(f"/api/paginas/{pagina['id']}/imagem").status_code == 200
        assert (config.DADOS / img).exists()

        # Excluir o documento apaga as imagens também do Storage.
        doc = e["docs"][0]
        chaves = [db.q("SELECT img FROM paginas WHERE id=?", (p["id"],), um=True)["img"]
                  for p in e["paginas"] if doc["pag_ini"] <= p["n"] <= doc["pag_fim"]]
        assert c.delete(f"/api/docs/{doc['id']}").status_code == 200
        assert not any(k in storage.objetos for k in chaves)


def test_sem_rede_o_envio_continua(monkeypatch, storage):
    def sem_rede(*a, **kw):
        raise ConnectionError("sem internet")
    monkeypatch.setattr(arquivos, "_requisicao", sem_rede)
    with TestClient(app) as c:
        entrar(c, "operador")
        r = c.post("/api/ws/atlantica/envios", files=[("arquivos", ("lote-offline.pdf", lote_pdf(), "application/pdf"))])
        e = esperar(c, r.json()["id"])
        arquivos.aguardar()
        assert e["envio"]["status"] == "concluido"


def test_envio_de_outro_computador_nao_e_processado_aqui():
    with TestClient(app) as c:
        entrar(c, "operador")
        r = c.post("/api/ws/atlantica/envios", files=[("arquivos", ("lote-outro.pdf", lote_pdf(), "application/pdf"))])
        eid = r.json()["id"]
        esperar(c, eid)
        db.x("UPDATE paginas SET status='pendente' WHERE envio_id=?", (eid,))
        db.x("UPDATE envios SET status='fila', servidor='outro-computador' WHERE id=?", (eid,))
        time.sleep(4)
        assert db.q("SELECT status FROM envios WHERE id=?", (eid,), um=True)["status"] == "fila"
        db.x("UPDATE envios SET servidor=? WHERE id=?", (config.SERVIDOR_ID, eid))  # devolve para este computador
        assert esperar(c, eid)["envio"]["status"] == "concluido"
