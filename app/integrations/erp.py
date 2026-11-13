"""Ponto de entrada da API ERP e dependências de autenticação máquina a máquina.

As rotas deste módulo não usam cookies/sessões humanas. Cada endpoint deve
declarar a dependência exigir_integracao(<escopo>) adequada à operação.
"""
from fastapi import APIRouter, Request

from .auth import autenticar_integracao, exigir_escopo


router = APIRouter(prefix="/api/erp/v1", tags=["Integração ERP"])


def exigir_integracao(escopo: str):
    """Cria dependência que valida Bearer Token e o escopo exigido pela rota.

    O workspace retornado vem exclusivamente do cadastro da credencial.
    Nunca deve ser substituído por um workspace enviado pelo ERP.
    """
    def dependencia(request: Request) -> dict:
        integracao = autenticar_integracao(request)
        exigir_escopo(integracao, escopo)
        return integracao

    return dependencia
