"""Caminhos, modelo e leitura do arquivo .env."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
# CONCILIA_DADOS permite outra pasta de dados (os testes usam uma pasta temporária).
DADOS = Path(os.environ.get("CONCILIA_DADOS") or (BASE / "dados"))
ENVIOS = DADOS / "envios"
PAGINAS = DADOS / "paginas"
BANCO = DADOS / "concilia.db"
WEB = BASE / "web"

for p in (DADOS, ENVIOS, PAGINAS):
    p.mkdir(parents=True, exist_ok=True)


def carregar_env():
    """Lê BASE/.env (CHAVE=valor) sem sobrescrever variáveis já definidas."""
    arq = BASE / ".env"
    if not arq.exists():
        return
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v and not os.environ.get(k.strip()):
            os.environ[k.strip()] = v


carregar_env()

MODELO = os.environ.get("CONCILIA_MODELO", "claude-opus-5-5")
# Limites por arquivo enviado. Um lote digitalizado de 100+ páginas em TIFF passa fácil de 50 MB.
MAX_MB = int(os.environ.get("CONCILIA_MAX_MB", "300"))
MAX_PAGINAS = int(os.environ.get("CONCILIA_MAX_PAGINAS", "2000"))
# Documentos por conta (somando todos os workspaces dela): decisão do time, novembro de 2026.
LIMITE_DOCUMENTOS = int(os.environ.get("CONCILIA_LIMITE_DOCUMENTOS", "100000"))
# Criar conta pela tela de login. Desligue (0) num servidor aberto na internet se não quiser cadastro livre.
CADASTRO_ABERTO = os.environ.get("CONCILIA_CADASTRO_ABERTO", "1") != "0"


def claude_configurado() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
