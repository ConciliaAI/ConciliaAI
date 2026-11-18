"""Acesso livre (avaliação): sem cookie, quem abre o link entra direto como o usuário de demonstração."""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app


@pytest.fixture
def cliente():
    with TestClient(app) as c:
        c.cookies.clear()
        yield c


def test_desligado_continua_exigindo_login(cliente, monkeypatch):
    monkeypatch.setattr(config, "ACESSO_LIVRE", False)
    assert cliente.get("/api/ws/horizonte/resumo").status_code == 401
    e = cliente.get("/api/estado").json()
    assert e["usuario"] is None and e["acesso_livre"] is False


def test_ligado_entra_direto_no_painel(cliente, monkeypatch):
    monkeypatch.setattr(config, "ACESSO_LIVRE", True)
    monkeypatch.setattr(config, "USUARIO_LIVRE", "admin")
    e = cliente.get("/api/estado").json()
    assert e["acesso_livre"] is True
    assert e["usuario"]["usuario"] == "admin" and e["clientes"]
    ws = e["clientes"][0]["id"]
    assert cliente.get(f"/api/ws/{ws}/resumo").status_code == 200


def test_ligado_com_usuario_inexistente_pede_login(cliente, monkeypatch):
    monkeypatch.setattr(config, "ACESSO_LIVRE", True)
    monkeypatch.setattr(config, "USUARIO_LIVRE", "ninguem")
    assert cliente.get("/api/estado").json()["usuario"] is None
    assert cliente.get("/api/ws/horizonte/resumo").status_code == 401
