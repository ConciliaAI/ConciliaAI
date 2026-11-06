# Concilia AI · Document AI Factory

Plataforma que recebe lotes de documentos misturados (PDF, fotos, TIFF, ZIP), descobre onde cada documento começa e termina, agrupa as páginas, classifica o tipo, lê o texto (OCR pesquisável), dá uma confiança para cada decisão e manda os casos duvidosos para revisão humana. Também retoma o processamento após falhas e esconde dados sensíveis. Cada cliente da Bernhoeft tem seu próprio workspace.

## Como abrir

Dê dois cliques em **iniciar.bat**. O navegador abre em http://127.0.0.1:8000.
Na primeira vez ele instala o que precisa (alguns minutos, precisa de internet).

## Contas de demonstração

| Usuário | Senha | Pode |
|---|---|---|
| admin | admin123 | tudo, inclusive configurações e avaliação |
| revisor | revisor123 | enviar, decidir pendências, ver dados protegidos |
| operador | operador123 | enviar e consultar |

Para trocar as senhas, coloque no `.env`: `CONCILIA_SENHA_ADMIN=...` (vale na primeira execução; depois, apague a pasta `dados`).

## Demonstração rápida

0. Entre como **admin**. Em **Acerto da IA** (cliente Atlântica Facilities), clique em **Gerar lote com gabarito e medir** e mostre o resultado.
1. Em **Enviar documentos**, clique em **Carregar lote de exemplo** (14 páginas misturadas, algumas tortas e borradas).
2. Enquanto processa, clique em **Simular queda**: o envio falha e retoma sozinho da página onde parou.
3. Veja a separação em documentos, com a confiança de cada um.
4. Em **Pendências**, responda as dúvidas da IA (teclas 1, 2, 3).
5. Em **Documentos**, veja a tabela por colaborador (Ok / Confirmar / Falta), abra um documento, baixe o PDF pesquisável.
6. Em **Busca**, procure por *hemograma*, *porteiro* ou *10/2026*.
7. Troque o cliente no topo (Construtora Vale Alto tem outro lote de exemplo).

## Ligar o Claude (IA multimodal)

1. Copie `.env.exemplo` para `.env`.
2. Cole a chave: `ANTHROPIC_API_KEY=sk-ant-...`
3. Feche e abra o **iniciar.bat** de novo.

Com a chave, cada página é lida pelo Claude (`claude-opus-5-5`) olhando **a imagem e o texto juntos**. Sem a chave, ou se o Claude falhar, a página usa a leitura local (OCR + regras), e isso fica anotado nos sinais da página.

## Onde fica cada coisa

| Pasta | O que tem |
|---|---|
| `app/` | Motor: OCR, análise, separação, anonimização, fila com retomada, API |
| `web/index.html` | As telas |
| `dados/` | Banco de dados e imagens das páginas (apague para recomeçar do zero) |
| `exemplos/` | Lotes de exemplo fictícios |
| `ferramentas/` | Gerador de exemplos e teste automático |
