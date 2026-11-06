"""Os testes da plataforma usam uma pasta de dados temporária (nunca a pasta dados/ real)."""
import os
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
