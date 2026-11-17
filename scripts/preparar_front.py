"""Monta o front novo (frontend/dist) para a API servir em http://127.0.0.1:8000.

Chamado pelo iniciar.bat e pelo iniciar.sh. Só refaz a montagem quando algo do front mudou desde a última
(ex.: depois de um git pull). Sem Node no computador, avisa e a plataforma abre com a versão anterior das telas.
"""
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
FRONT = RAIZ / "frontend"
PRONTO = FRONT / "dist" / "index.html"


def mais_novo(arquivo: Path) -> float:
    return arquivo.stat().st_mtime if arquivo.exists() else 0.0


def fontes_mudaram() -> bool:
    if not PRONTO.exists():
        return True
    feito = mais_novo(PRONTO)
    fontes = [FRONT / n for n in ("index.html", "package.json", "package-lock.json", "vite.config.js")]
    for pasta in (FRONT / "src", FRONT / "public"):
        fontes += [p for p in pasta.rglob("*") if p.is_file()]
    return any(mais_novo(f) > feito for f in fontes)


def rodar(*cmd) -> bool:
    print("  >", " ".join(cmd), flush=True)
    return subprocess.run(list(cmd), cwd=FRONT, shell=sys.platform == "win32").returncode == 0


def main() -> int:
    if not fontes_mudaram():
        print("Front novo já está pronto.")
        return 0
    npm = shutil.which("npm")
    if not npm:
        print("AVISO: Node.js não encontrado. A plataforma abre com a versão anterior das telas.")
        print("       Para o front novo, instale o Node.js LTS em nodejs.org e abra de novo.")
        return 0
    print("Montando o front novo (só quando ele muda; leva uns segundos)...")
    precisa_instalar = mais_novo(FRONT / "package-lock.json") > mais_novo(FRONT / "node_modules" / ".package-lock.json")
    if precisa_instalar and not rodar("npm", "install", "--no-audit", "--no-fund", "--loglevel=error"):
        print("AVISO: não foi possível instalar as dependências do front. Abrindo a versão anterior das telas.")
        return 0
    if not rodar("npm", "run", "build", "--", "--logLevel", "error"):
        print("AVISO: a montagem do front falhou. Abrindo o que já estava montado (ou a versão anterior das telas).")
        return 0
    print("Front novo pronto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
