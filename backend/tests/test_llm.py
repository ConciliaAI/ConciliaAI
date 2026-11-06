"""Integração com o Claude sem chamada paga: a resposta da API é simulada."""
from app import llm
from app.config import get_settings


def page(number, text, confidence=0.99):
    return {"number": number, "text": text, "confidence": confidence}


# Contrato sem os rótulos que as regras locais esperam: só o Claude consegue ler.
CONTRATO_LIVRE = """CONTRATO DE PRESTACAO DE SERVICOS
A empresa Limpa Bem Ltda, inscrita no CNPJ 87.000.001/1001-78, prestara servicos de limpeza
pelo valor de R$ 8.000,00 por mes, de 01/01/2026 a 31/12/2026."""


def vazio():
    return {"value": "", "page": 0, "excerpt": ""}


def resposta(kind="contrato", confidence=0.9, **campos):
    fields = {k: vazio() for k in llm.TODOS}
    fields.update(campos)
    return {"kind": kind, "confidence": confidence, "reasons": ["Título de contrato"], "fields": fields}


def ligar(monkeypatch, dados=None, erro=None):
    monkeypatch.setattr(get_settings(), "llm_api_key", "teste")

    def falso(paginas, tipo_local):
        if erro:
            raise erro
        return dados

    monkeypatch.setattr(llm, "_chamar", falso)


def test_sem_chave_usa_so_regras_locais(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_api_key", "")
    kind, conf, reasons, fields = llm.analisar([page(1, CONTRATO_LIVRE)], "contrato", 0.86, ["local"])
    assert (kind, conf, reasons) == ("contrato", 0.86, ["local"])
    assert "value" not in fields


def test_claude_extrai_campos_com_evidencia(monkeypatch):
    ligar(monkeypatch, resposta(
        supplier_cnpj={"value": "87.000.001/1001-78", "page": 1, "excerpt": "CNPJ 87.000.001/1001-78"},
        value={"value": "8000.00", "page": 1, "excerpt": "R$ 8.000,00 por mes"},
        validity_start={"value": "2026-01-01", "page": 1, "excerpt": "de 01/01/2026 a 31/12/2026"},
        validity_end={"value": "2026-12-31", "page": 1, "excerpt": "de 01/01/2026 a 31/12/2026"},
    ))
    kind, conf, reasons, fields = llm.analisar([page(1, CONTRATO_LIVRE)], "contrato", 0.86, [])
    assert kind == "contrato" and conf == 0.9
    assert fields["supplier_cnpj"]["value"] == "87000001100178"
    assert fields["value"] == {"value": "8000.00", "page": 1, "excerpt": "R$ 8.000,00 por mes",
                               "confidence": 0.99, "source": "claude"}
    assert fields["validity"]["value"] == ["2026-01-01", "2026-12-31"]


def test_trecho_inventado_baixa_confianca(monkeypatch):
    ligar(monkeypatch, resposta(value={"value": "9000.00", "page": 1, "excerpt": "R$ 9.000,00 mensais"}))
    _, _, _, fields = llm.analisar([page(1, CONTRATO_LIVRE)], "contrato", 0.86, [])
    assert fields["value"]["confidence"] == 0.5


def test_discordancia_de_tipo_vai_para_revisao(monkeypatch):
    ligar(monkeypatch, resposta(kind="aditivo_contratual", confidence=0.95))
    kind, conf, reasons, _ = llm.analisar([page(1, CONTRATO_LIVRE)], "contrato", 0.86, [])
    assert kind == "aditivo_contratual" and conf == 0.6
    assert any("Regras locais diziam contrato" in r for r in reasons)


def test_falha_do_claude_nao_trava_o_lote(monkeypatch):
    ligar(monkeypatch, erro=TimeoutError("sem rede"))
    kind, conf, reasons, _ = llm.analisar([page(1, CONTRATO_LIVRE)], "contrato", 0.86, [])
    assert (kind, conf) == ("contrato", 0.86)
    assert "Claude indisponível; usada a leitura local" in reasons
