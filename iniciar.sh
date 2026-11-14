#!/usr/bin/env bash
# ==============================================================================
# Concilia AI - Script de Inicialização para Linux (Nativo & VS Code Flatpak)
# Equivalente ao iniciar.bat (Windows)
# ==============================================================================

set -e

# Garante que o diretório de trabalho é a raiz do projeto
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Evita que PYTHONHOME global interfira na resolução do ambiente virtual
unset PYTHONHOME

# Configura diretório temporário no /home para evitar estouro de espaço em disco no /tmp
export TMPDIR="$SCRIPT_DIR/.tmp"
mkdir -p "$TMPDIR"
trap 'rm -rf "$SCRIPT_DIR/.tmp"' EXIT

# Cores para o terminal
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
VERMELHO='\033[0;31m'
AZUL='\033[0;34m'
SEM_COR='\033[0m'

echo -e "${AZUL}========================================${SEM_COR}"
echo -e "${AZUL}       Concilia AI · Inicialização      ${SEM_COR}"
echo -e "${AZUL}========================================${SEM_COR}"

# 1. Detecta o interpretador Python da sessão atual
PYTHON_CMD=""
if command -v python3 &>/dev/null; then
    PYTHON_CMD="python3"
elif command -v python &>/dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${VERMELHO}Erro: Python 3 não encontrado no sistema.${SEM_COR}"
    echo "Por favor, instale o Python 3.11 ou superior:"
    echo "  Ubuntu/Debian: sudo apt update && sudo apt install -y python3 python3-venv python3-pip"
    echo "  Fedora:        sudo dnf install -y python3 python3-pip"
    echo "  Arch Linux:    sudo pacman -S python python-pip"
    exit 1
fi

PY_VER=$($PYTHON_CMD -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.major)")
PY_MINOR=$($PYTHON_CMD -c "import sys; print(sys.version_info.minor)")

if [ "$PY_MAJOR" -lt 3 ] || ([ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]); then
    echo -e "${VERMELHO}Erro: Python $PY_VER detectado. É necessário Python 3.11 ou superior.${SEM_COR}"
    exit 1
fi

# 2. Verifica compatibilidade do .venv existente com a versão atual do Python
if [ -f ".venv/pyvenv.cfg" ]; then
    VENV_VER=$(grep "^version" .venv/pyvenv.cfg | cut -d'=' -f2 | tr -d ' ' | cut -d'.' -f1,2 || true)
    if [ -n "$VENV_VER" ] && [ "$VENV_VER" != "$PY_VER" ]; then
        echo -e "${AMARELO}Detectada mudança de ambiente (Python do .venv: $VENV_VER vs Terminal: $PY_VER).${SEM_COR}"
        echo -e "${AMARELO}Recriando o ambiente virtual para ser 100% compatível com este terminal...${SEM_COR}"
        rm -rf .venv
    fi
fi

# Se o .venv/bin/python existir mas não conseguir importar pip, está quebrado
if [ -f ".venv/bin/python" ] && ! .venv/bin/python -c "import pip" &>/dev/null; then
    echo -e "${AMARELO}Ambiente virtual incompatível com o interpretador atual. Recriando...${SEM_COR}"
    rm -rf .venv
fi

# 3. Criação do .venv se necessário
if [ ! -f ".venv/bin/python" ]; then
    echo -e "${AMARELO}Criando ambiente virtual (.venv) com Python $PY_VER...${SEM_COR}"
    if ! $PYTHON_CMD -m venv .venv; then
        echo -e "${VERMELHO}Falha ao criar o ambiente virtual com venv.${SEM_COR}"
        echo "Em distribuições Debian/Ubuntu, você pode precisar instalar o pacote python3-venv:"
        echo "  sudo apt install -y python3-venv"
        exit 1
    fi
fi

# 4. Verifica se as bibliotecas essenciais estão instaladas
if ! .venv/bin/python -c "import uvicorn, fastapi, pymupdf" &>/dev/null; then
    echo -e "${AMARELO}Instalando as dependências da Concilia AI (requirements.txt)...${SEM_COR}"
    echo "Isso leva alguns minutos e requer conexão com a internet."

    echo "Atualizando o pip..."
    .venv/bin/python -m pip install -q --no-cache-dir --upgrade pip

    echo "Instalando pacotes..."
    if ! .venv/bin/python -m pip install -q --no-cache-dir -r requirements.txt; then
        echo -e "${VERMELHO}Falha ao instalar as bibliotecas. Verifique a conexão com a internet.${SEM_COR}"
        exit 1
    fi
    echo -e "${VERDE}Ambiente configurado com sucesso!${SEM_COR}"
fi

# 5. Configura arquivo .env se não existir
if [ ! -f ".env" ] && [ -f ".env.exemplo" ]; then
    echo -e "${AMARELO}Arquivo .env não encontrado. Criando cópia inicial a partir de .env.exemplo...${SEM_COR}"
    cp .env.exemplo .env
fi

# 5b. Bibliotecas novas depois de um git pull (rápido quando já está tudo instalado)
.venv/bin/python -m pip install -q --disable-pip-version-check --no-cache-dir -r requirements.txt || {
    echo -e "${VERMELHO}Falha ao atualizar as bibliotecas. Verifique a conexão com a internet.${SEM_COR}"
    exit 1
}

# 5c. Monta o front novo quando ele mudou; a própria API serve as telas em http://127.0.0.1:8000
.venv/bin/python scripts/preparar_front.py

# 6. Informações de execução
URL="http://127.0.0.1:8000"
echo ""
echo -e "${VERDE}✔ Concilia AI pronta e iniciando em:${SEM_COR} ${AZUL}${URL}${SEM_COR}"
echo -e "Para parar o servidor, pressione ${AMARELO}Ctrl+C${SEM_COR}."
echo ""

# 7. Tenta abrir o navegador se houver ambiente gráfico disponível
if [ -n "$DISPLAY" ] || [ -n "$WAYLAND_DISPLAY" ]; then
    if command -v xdg-open &>/dev/null; then
        (sleep 1.5 && xdg-open "$URL" >/dev/null 2>&1) &
    fi
fi

# 8. Executa o servidor FastAPI com Uvicorn
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
