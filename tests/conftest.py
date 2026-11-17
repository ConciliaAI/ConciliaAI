"""Os testes da plataforma usam uma pasta de dados temporária (nunca a pasta dados/ real)."""
import os
import secrets
import sys
import tempfile
from pathlib import Path

os.environ["CONCILIA_DADOS"] = tempfile.mkdtemp(prefix="concilia-teste-")
os.environ["CONCILIA_SEGREDO"] = "segredo-de-teste"
os.environ["ANTHROPIC_API_KEY"] = ""  # testes sempre usam a leitura local
# Senhas próprias dos testes (as do .env, usadas no sistema de verdade, não valem aqui).
for _u in ("admin", "revisor", "operador"):
    os.environ[f"CONCILIA_SENHA_{_u.upper()}"] = f"{_u}123"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Banco dos testes: SQLite temporário, mesmo que o .env tenha DATABASE_URL (os testes nunca gravam no banco real).
# Para rodar no Postgres: CONCILIA_TESTE_POSTGRES=postgresql://... (ou =env para usar a DATABASE_URL do .env).
# Os testes usam então um esquema temporário (teste_xxxx), apagado no fim.
_pg = os.environ.get("CONCILIA_TESTE_POSTGRES", "").strip()
if _pg == "env":
    _env = Path(__file__).resolve().parent.parent / ".env"
    _linhas = _env.read_text(encoding="utf-8").splitlines() if _env.exists() else []
    _pg = next((ln.split("=", 1)[1].strip().strip('"').strip("'") for ln in _linhas
                if ln.strip().startswith("DATABASE_URL=")), "")
if _pg:
    os.environ["DATABASE_URL"] = _pg
    os.environ["CONCILIA_PG_ESQUEMA"] = f"teste_{secrets.token_hex(4)}"
else:
    os.environ["DATABASE_URL"] = "sqlite"  # não vazio: o .env não sobrescreve
# Os testes nunca usam o Storage de verdade (test_arquivos.py simula um em memória).
os.environ["SUPABASE_URL"] = " "
os.environ["SUPABASE_SECRET_KEY"] = " "


def pytest_sessionfinish(session, exitstatus):
    """Apaga o esquema temporário dos testes no Postgres."""
    if os.environ.get("DATABASE_URL", "").startswith(("postgres://", "postgresql://")):
        from app import db
        with db._lock:
            db._con.execute(f"DROP SCHEMA IF EXISTS {os.environ['CONCILIA_PG_ESQUEMA']} CASCADE")
