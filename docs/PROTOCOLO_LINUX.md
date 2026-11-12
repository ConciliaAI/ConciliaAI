# Protocolo de Execução e Inicialização no Linux · Concilia AI

Este documento detalha a revisão técnica da base de código para ambientes **Linux** e estabelece o protocolo padrão de preparação, execução e manutenção do servidor.

---

## 1. Revisão da Base de Código (Diagnóstico de Compatibilidade)

Após auditoria completa do repositório, identificamos os seguintes pontos de arquitetura e compatibilidade:

| Componente | Status no Linux | Observações Técnicas |
|---|---|---|
| **Caminhos de Arquivos (`app/config.py`, `app/pipeline.py`)** | ✅ 100% Compatível | Utiliza `pathlib.Path` de forma idiomática; não há concatenações manuais de caminhos com barras invertidas (`\`). |
| **Banco de Dados SQLite (`app/db.py`)** | ✅ 100% Compatível | Arquivo local `dados/concilia.db` com `PRAGMA journal_mode=WAL` e `foreign_keys=ON`. Criação e bloqueio de arquivos POSIX funcionam nativamente. |
| **Motor de OCR Local (`app/ocr.py`)** | ✅ 100% Compatível | `rapidocr-onnxruntime` e `onnxruntime` rodam via CPU sem necessidade de binários externos ou Tesseract instalado no sistema. |
| **Manipulação de PDF e Imagens (`pymupdf`, `Pillow`)** | ✅ 100% Compatível | Bibliotecas compiladas (wheels) disponíveis e testadas com sucesso em distribuições Linux x86_64. |
| **Web / Telas (`app/main.py`, `web/index.html`)** | ✅ 100% Compatível | FastAPI serve o arquivo estático `web/index.html` na porta 8000 sem etapa prévia de build. |
| **Frontend React (`frontend/`)** | ✅ 100% Compatível | Node.js + Vite (`npm run dev`) na porta 5173 com proxy reverso apontando para `http://127.0.0.1:8000/api`. |
| **Testes Automatizados (`tests/`)** | ✅ 100% Compatível | Todos os 48 testes unitários e de integração passaram com sucesso no Linux (`pytest`). |
| **Scripts de Inicialização** | ⚠️ Paridade Criada | Existia apenas `iniciar.bat` (Windows). Foi criado o script nativo correspondente `iniciar.sh` com permissão de execução (`chmod +x`). |

---

## 2. Pré-requisitos do Sistema Operacional

Recomenda-se **Python 3.11** ou superior (compatível até Python 3.14).

### Instalação dos pacotes básicos por distribuição

- **Ubuntu / Debian / Linux Mint:**
  ```bash
  sudo apt update
  sudo apt install -y python3 python3-venv python3-pip xdg-utils
  ```

- **Fedora / RHEL / CentOS Stream:**
  ```bash
  sudo dnf install -y python3 python3-pip xdg-utils
  ```

- **Arch Linux / Manjaro:**
  ```bash
  sudo pacman -S python python-pip xdg-utils
  ```

---

## 3. Protocolo de Inicialização

### Método A: Inicialização Automática (Recomendado)

Assim como o `iniciar.bat` no Windows, o script `iniciar.sh` automatiza todo o ciclo de vida inicial:
1. Criação do ambiente virtual `.venv` caso ainda não exista.
2. Atualização do `pip` e instalação de dependências do `requirements.txt`.
3. Criação automática do arquivo de configuração `.env` a partir de `.env.exemplo` (caso ausente).
4. Abertura automática da URL no navegador padrão via `xdg-open` (se interface gráfica estiver ativa).
5. Execução do servidor FastAPI através do Uvicorn na porta 8000.

#### Execução:
```bash
./iniciar.sh
```

> **Nota:** Caso o arquivo não tenha permissão de execução, conceda com:
> ```bash
> chmod +x iniciar.sh
> ```

---

### Método B: Inicialização Manual (Passo a Passo)

Para controle detalhado do ambiente, execute os passos abaixo no terminal:

#### 1. Clonar ou navegar até o diretório do projeto:
```bash
cd /caminho/para/ConciliaAI
```

#### 2. Criar e ativar o ambiente virtual:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. Atualizar ferramentas e instalar dependências:
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

#### 4. Configurar as variáveis de ambiente:
```bash
if [ ! -f .env ]; then
    cp .env.exemplo .env
fi
```
*(Opcional: edite o `.env` para inserir sua chave `ANTHROPIC_API_KEY` se desejar usar a IA multimodal Claude, ou personalize `CONCILIA_SENHA_ADMIN`)*.

#### 5. Iniciar o servidor com Uvicorn:
```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Acesse no navegador:
**http://127.0.0.1:8000**

---

## 4. Execução de Testes e Ferramentas Auxiliares

No Linux, todas as chamadas utilizam `.venv/bin/python` em vez de `.venv\Scripts\python.exe`:

### Executar a suíte de testes:
```bash
.venv/bin/pytest -v
```

### Gerar arquivos fictícios para demonstração (`casos-de-teste/`):
```bash
.venv/bin/python ferramentas/gerar_casos_teste.py 20
```

### Medir acerto contra gabarito:
```bash
.venv/bin/python ferramentas/medir_acerto.py
```

### Medir consumo e custos com Claude (requer chave no `.env`):
```bash
.venv/bin/python ferramentas/medir_custo_ia.py --paginas 10 --modelos opus,sonnet,haiku --dolar 5.40
```

---

## 5. Execução do Frontend Moderno (React + Tailwind)

O novo frontend (em `frontend/`) consome a API do servidor principal:

1. Deixe o servidor rodando na porta 8000 (`./iniciar.sh` ou via terminal).
2. Em outro terminal:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
3. Acesse o frontend novo em: **http://localhost:5173**

---

## 6. Execução em Servidor Dedicado / Produção (systemd)

Para manter o serviço em execução contínua no Linux, crie uma unidade de serviço no systemd:

```ini
# /etc/systemd/system/concilia-ai.service
[Unit]
Description=Concilia AI - Document AI Factory
After=network.target

[Service]
Type=simple
User=seu-usuario
WorkingDirectory=/caminho/para/ConciliaAI
ExecStart=/caminho/para/ConciliaAI/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5
EnvironmentFile=/caminho/para/ConciliaAI/.env

[Install]
WantedBy=multi-user.target
```

Ative e inicie com:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now concilia-ai
sudo systemctl status concilia-ai
```

---

## 7. Solução de Problemas Comuns (Troubleshooting)

| Sintoma | Causa | Solução |
|---|---|---|
| `The virtual environment was not created successfully because ensurepip is not available` | Pacote `python3-venv` ausente no Ubuntu/Debian | Execute `sudo apt install python3-venv` |
| `Permission denied: ./iniciar.sh` | Falta permissão de execução | Execute `chmod +x iniciar.sh` |
| `Address already in use` (Porta 8000 ocupada) | Outro processo está usando a porta 8000 | Descubra e encerre com: `lsof -i :8000` e `kill <PID>` ou defina outra porta: `uvicorn app.main:app --port 8080` |
| `xdg-open: no method available for opening 'http://...'` | Terminal sem interface gráfica / SSH remoto | Normal em servidores sem tela; abra o link manualmente no navegador da sua máquina local. |
| Dados persistidos corrompidos ou deseja reiniciar do zero | Deseja limpar banco e envios | Pare o servidor e remova a pasta: `rm -rf dados/` (o sistema recria automaticamente no próximo início) |
