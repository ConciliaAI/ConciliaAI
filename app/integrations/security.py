"""Primitivas de segurança para credenciais de integrações ERP."""
import hashlib
import hmac
import secrets


PREFIXO_TOKEN = "cai_"


def gerar_token() -> str:
    """Gera uma credencial aleatória; o valor puro só é exibido na criação/rotação."""
    return PREFIXO_TOKEN + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def token_confere(token: str, hash_guardado: str) -> bool:
    return hmac.compare_digest(hash_token(token), hash_guardado)
