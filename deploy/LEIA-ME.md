# Deploy da Concilia AI numa VPS

A Concilia roda em um contêiner Docker (o `Dockerfile` na raiz monta o front e a API). Na VPS da Hostinger
ela fica em `/opt/concilia-ai`, atrás do Caddy, que já cuida do HTTPS dos outros sites do servidor.

| O quê | Onde |
|---|---|
| Código | `/opt/concilia-ai/app` (clone do GitHub) |
| Configuração do contêiner | `/opt/concilia-ai/docker-compose.yml` (exemplo em `deploy/docker-compose.yml`) |
| Senhas e chaves | `/opt/concilia-ai/.env` (só o root lê; nunca vai para o Git) |
| Dados (banco e páginas) | volume Docker `concilia-ai_dados` |
| Endereço | porta interna `127.0.0.1:8095`, publicada pelo Caddy em `https://concilia.2.25.226.129.nip.io` |
| Log do último deploy | `/opt/concilia-ai/deploy.log` |

## Variáveis do `.env`

| Variável | Para quê |
|---|---|
| `CONCILIA_SENHA_ADMIN`, `CONCILIA_SENHA_REVISOR`, `CONCILIA_SENHA_OPERADOR` | Senhas das contas de demonstração (geradas no servidor com `openssl rand`) |
| `CONCILIA_SEGREDO` | Assina o cookie de login |
| `CONCILIA_SERVIDOR` | Nome deste servidor na fila de processamento |
| `ANTHROPIC_API_KEY` | Liga a leitura com o Claude. Vazia, a Concilia usa só o OCR local |

Para ver as senhas: `grep SENHA /opt/concilia-ai/.env` (como root).

## Atualizar depois de um push

```bash
cd /opt/concilia-ai/app && git pull && cd .. && docker compose up -d --build
```

## Ligar o Claude

Edite `/opt/concilia-ai/.env`, preencha `ANTHROPIC_API_KEY=` e rode `docker compose up -d` na mesma pasta.

## Tirar tudo do servidor

```bash
cd /opt/concilia-ai && docker compose down -v && cd / && rm -rf /opt/concilia-ai
cp /etc/caddy/Caddyfile.antes-concilia /etc/caddy/Caddyfile && systemctl reload caddy
```

O primeiro comando apaga o contêiner e os dados; o segundo devolve o Caddy ao que era antes da Concilia.
