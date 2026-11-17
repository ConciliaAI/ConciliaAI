# Concilia AI · Document AI Factory

Plataforma que recebe lotes digitalizados grandes e misturados (TIFF multipágina, PDF, fotos, ZIP, até 300 MB por arquivo), descobre onde cada documento começa e termina, agrupa as páginas, classifica o tipo, lê o texto (OCR pesquisável), dá uma confiança para cada decisão e manda os casos duvidosos para revisão humana. Retoma o processamento após falhas e esconde dados sensíveis. Cada cliente da Bernhoeft tem seu próprio workspace.

**Foco: a nota fiscal de serviço.** Os documentos do lote são notas (NFS-e), contratos e aditivos de fornecedores terceirizados. O XML da NFS-e é lido direto, sem OCR. Como diferencial, cada nota é conferida contra o contrato (valor, vigência, aditivos, serviço, duplicidade) e as divergências vão para decisão humana.

## Requisitos mínimos do Desafio 3: onde ver

| Requisito | Onde ver na demo |
|---|---|
| Detecção de início e fim | Envios → Ver: a borda escura marca a 1ª página de cada documento |
| Agrupamento de páginas | Envios → Ver: páginas do mesmo documento aparecem juntas |
| Classificação por tipo | Documentos; Acerto da IA mede contra o gabarito |
| OCR pesquisável | Busca (ex.: *limpeza*, *CTR-001*) e "Baixar PDF pesquisável" no documento |
| Confiança e fila de revisão | Barra de confiança em cada documento; abaixo de 75% vai para **Dúvidas da leitura** |
| Diferenciais | Simular queda (retomada), dados protegidos (anonimização), Claude multimodal com chave |

## Como abrir

- **Linux:** Execute `./iniciar.sh` no terminal (veja o [Protocolo Linux](docs/PROTOCOLO_LINUX.md)).
- **Windows:** Dê dois cliques em **`iniciar.bat`**.

O navegador abre em http://127.0.0.1:8000. Na primeira vez ele instala o que precisa (alguns minutos, precisa de internet).

## Contas de demonstração

| Usuário | Senha | Pode |
|---|---|---|
| admin | admin123 | tudo, inclusive configurações e avaliação |
| revisor | revisor123 | enviar, decidir pendências, ver dados protegidos |
| operador | operador123 | enviar e consultar |

Para trocar as senhas, coloque no `.env`: `CONCILIA_SENHA_ADMIN=...` (vale ao reabrir o sistema). Troque sempre antes de compartilhar um link público.

## Demonstração rápida (lote fictício)

1. Entre como **admin**. Em **Enviar documentos**, clique em **Carregar lote de exemplo**: gera um TIFF digitalizado de ~100 páginas (contratos, aditivos e notas misturados, algumas folhas tortas e borradas) + o XML de cada nota.
2. Enquanto processa, clique em **Simular queda**: falha e retoma sozinho da página onde parou.
3. Veja a separação em documentos com a confiança de cada um.
4. Em **Dúvidas da leitura**, responda o que a IA não teve certeza (teclas 1, 2, 3).
5. Em **Divergências**, aprove ou rejeite as notas que não batem com o contrato.
6. Em **Busca**, procure *limpeza* ou *CTR-002*. Em **Acerto da IA**, gere um lote com gabarito e mostre os números.

O processamento usa a CPU do computador: conte uns 2 a 3 segundos por página digitalizada sem a chave do Claude.

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
| `app/fiscal.py`, `app/conciliacao.py` | Leitura da NFS-e e dos contratos; regras de conferência |
| `ferramentas/medir_acerto.py` | Mede o acerto com um lote com gabarito (servidor aberto) |

## Casos de teste para a demonstração

Gere a pasta `casos-de-teste/` (todos os arquivos dos mesmos fornecedores fictícios):

```bash
# Linux:
.venv/bin/python ferramentas/gerar_casos_teste.py

# Windows:
.venv\Scripts\python.exe ferramentas\gerar_casos_teste.py
```

| Arquivo | O que mostra |
|---|---|
| `01-lote-grande-304-paginas.tif` | Grande volume só de imagem: separação, OCR, confiança, fila de revisão, retomada |
| `02-notas-do-lote-xml.zip` | 60 NFS-e em XML conferidas contra os contratos do 01 |
| `03-contrato-...-pagina-repetida.pdf` | "Página repetida: a página 4 de 9 aparece 2 vezes" → revisão |
| `04-contrato-...-falta-pagina-6.pdf` | "Documento incompleto: falta a página 6 de 9" → revisão |
| `05-nota-...-folha-cortada.pdf` | Folha cortada: valor ilegível, nota não entra pela imagem (use o XML) |
| `06` a `09` (XML) | Nota reenviada (não duplica), mesmo número, valor acima, fornecedor sem contrato |

O roteiro completo e o resultado esperado de cada um ficam em `casos-de-teste/LEIA-ME.txt`. O 01 leva uns 6 segundos por página: processe antes da apresentação e mostre ao vivo só os arquivos pequenos.

## Link para outras pessoas acessarem

Com o sistema aberto, rode num segundo terminal:

```cmd
.externos\cloudflared.exe tunnel --no-autoupdate --url http://127.0.0.1:8000
```

Ele mostra um endereço `https://….trycloudflare.com`. O link funciona enquanto o notebook e os dois programas estiverem abertos e muda a cada vez. Antes, troque as senhas no `.env`. O `cloudflared.exe` oficial fica em github.com/cloudflare/cloudflared (versão Windows amd64).

## Medir o custo real da IA (Claude)

Com a chave no `.env` (`ANTHROPIC_API_KEY=...`), rode:

```bash
# Linux:
.venv/bin/python ferramentas/medir_custo_ia.py --paginas 10 --modelos opus,sonnet,haiku --dolar 5.40

# Windows:
.venv\Scripts\python.exe ferramentas\medir_custo_ia.py --paginas 10 --modelos opus,sonnet,haiku --dolar 5.40
```

Ele faz chamadas reais (pagas, centavos) com as páginas do lote digitalizado, soma os tokens que a API informa em cada resposta e mostra o custo por página e por 1 mil, 10 mil e 100 mil páginas, com e sem o modo "só as duvidosas". O resultado fica em `casos-de-teste/custo-ia-medido.json`. Preços usados (US$ por milhão de tokens, entrada/saída): Opus 5.5 4/20, Sonnet 5.5 2/10, Haiku 5.5 0,10/0,50.
