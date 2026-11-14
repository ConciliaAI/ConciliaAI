# Concilia AI

**Hack Garanhuns Tech 2026 · Desafio 3 — Document AI Factory (desafio proposto pela Bernhoeft)**

A Concilia AI recebe lotes grandes de documentos digitalizados e misturados, descobre onde cada documento começa e termina, agrupa as páginas, classifica o tipo, deixa o texto pesquisável (OCR) e manda para revisão humana o que não tem certeza. O foco é o documento que mais pesa na gestão de terceiros: a **nota fiscal de serviço (NFS-e)**, conferida contra o contrato do fornecedor. Também lê o XML de **NF-e (55), NFC-e (65) e CT-e (57)**, recebe documentos direto do **ERP** do cliente e tem um **scanner pela câmera** do celular.

> Ferramenta de apoio à conferência documental. Aponta diferenças e mostra de onde elas vêm; não substitui análise jurídica, contábil ou tributária.

## O problema

Grandes empresas contratam dezenas de micro e pequenas empresas. Cada uma manda contratos, aditivos e notas fiscais, muitas vezes digitalizados, fora de ordem e num arquivo só. Alguém precisa separar, ler e conferir se o que foi cobrado bate com o que foi contratado. Desde 01/11/2026 (Resolução CGSN nº 191/2026, premissa da proposta), MEI e empresas do Simples emitem NFS-e só pelo Emissor Nacional: o XML padronizado facilita a conferência automática.

## Como abrir

- **Linux:** Execute `./iniciar.sh` no terminal (veja o [Protocolo detalhado para Linux](docs/PROTOCOLO_LINUX.md)).
- **Windows:** Dê dois cliques em **`iniciar.bat`**.

Ele instala ou atualiza as bibliotecas, monta as telas e abre o navegador em **http://127.0.0.1:8000**. Precisa de Python 3.11+ e Node.js (para montar as telas; sem Node, abre a versão anterior delas). Deixe a janela aberta enquanto usa. Roteiro de teste para o time: **[docs/ROTEIRO_DE_TESTE.md](docs/ROTEIRO_DE_TESTE.md)**.

| Usuário | Senha | Pode |
|---|---|---|
| admin | admin123 | tudo: workspaces, usuários, integrações, configurações e avaliação |
| revisor | revisor123 | decidir dúvidas e divergências, avisar fornecedores, ver dados protegidos |
| operador | operador123 | enviar documentos e consultar |

São as contas da empresa de demonstração (senhas trocáveis no `.env`). Outra empresa entra por **Criar conta**, na tela de login, e cria um workspace para cada cliente. Banco no Supabase: **[docs/SUPABASE.md](docs/SUPABASE.md)**.

Roteiro da demonstração em **[LEIA-ME.md](LEIA-ME.md)**.

### Front novo (React + Tailwind)

As telas foram refeitas em `frontend/` (Vite, React, Tailwind, JavaScript), seguindo os layouts do Figma, e a API as serve em http://127.0.0.1:8000 (o `iniciar.bat` monta tudo).

Para mexer nas telas com recarga automática, ou testar o scanner no celular (a câmera exige https), rode também `cd frontend`, `npm install` e `npm run dev`: abre em **https://localhost:5173**, com um certificado de teste (na primeira vez: **Avançado → Continuar para localhost**). No celular, na mesma rede Wi-Fi, use o endereço "Network" que aparecer.

| Tela | O que faz |
|---|---|
| Login | Entrada com o painel da marca e a prévia do dashboard |
| Documentos (dashboard) | Bloco do scanner logo no topo, números do lote, pastas por tipo, tabela com filtro e exclusão, fila "Precisam de você" |
| Enviar documentos | Arrastar o lote, progresso página a página com miniaturas, pausar, retomar e cancelar, histórico com o resultado de cada envio |
| Revisão humana | Uma fila só com as dúvidas da leitura e as divergências nota × contrato; páginas lado a lado, respostas com atalhos 1, 2 e 3 |
| Documento | Página do documento, divergência com os valores, confiança da leitura e campos lidos; aprovar, rejeitar, baixar PDF e excluir |
| Busca | Busca no texto de todos os documentos, com os dados protegidos mascarados |
| Contratos | Contratos lidos, vigência (vencidos e a vencer), notas e divergências de cada um, aditivos e busca |
| Relatórios | Notas conferidas no mês (gráfico por situação), divergências por regra e as planilhas para baixar em CSV |
| XML fiscais | NF-e, NFC-e e CT-e importados: filtro por modelo e detalhes com emitente, destinatário, itens, tributos e validação |
| Scanner | "Escanear agora" no dashboard abre a câmera (traseira ou frontal), mostra a prévia e envia a foto para a leitura |
| Configurações | Abas: geral (IA, limite de confiança, tolerância e regras), dados protegidos, tipos de documento, usuários da empresa, integração com ERP e acerto da IA |
| Ajuda | O caminho de um documento, o que a Concilia faz e perguntas frequentes |
| Criar conta e workspaces | Cadastro da empresa no login; seletor de cliente na barra do topo e "Novo workspace" |

Todas as telas estão no front novo; a pasta `web/` guarda a versão anterior, usada só quando o computador não tem Node. A interface escala junto com a largura e a altura da janela, mantendo as proporções do Figma (1440 px). Listas longas (fila de revisão, tabela de documentos) rolam por dentro e a tabela mostra 100 documentos por vez, pensando no limite de 100 mil documentos por conta.

## Requisitos do Desafio 3

| Capacidade mínima | Como funciona | Onde ver |
|---|---|---|
| Detecção de início e fim | Cada página recebe "começa um novo" ou "continua", por título, numeração ("2 de 9"), tipo e mudança de fornecedor | Enviar documentos → Ver envio |
| Agrupamento de páginas | Páginas seguidas do mesmo documento viram um documento | Ver envio, Documentos |
| Classificação por tipo | Nota fiscal, contrato, aditivo, medição, comprovante; novos tipos podem ser ensinados | Documentos, Configurações |
| OCR pesquisável | OCR local (RapidOCR) em toda página de imagem; busca no texto e download de PDF pesquisável | Busca, Documentos |
| Confiança e fila de revisão | Confiança por página e documento; abaixo de 75% vai para **Dúvidas da leitura**, mostrando qual página derrubou a confiança e por quê | Dúvidas da leitura |

| Diferencial | Como funciona |
|---|---|
| Multimodal | Com `ANTHROPIC_API_KEY` no `.env`, o Claude lê **imagem + texto** de cada página e extrai os campos dos contratos. Sem chave ou se falhar, usa a leitura local |
| Retomada após falha | Cada página é salva ao terminar; queda ou fechamento continua da próxima. Botão "Simular queda" |
| Anonimização | CPF/RG, conta, saúde, endereço e contato escondidos no texto, na busca, na imagem e no PDF; ver o original exige motivo, registrado |

## Conferência das notas (o diferencial da proposta)

1. **XML da NFS-e** (leiaute nacional, ABRASF ou de teste) é lido direto, sem OCR. Nota em PDF também é aceita.
2. **Contratos e aditivos** passam pela separação e pelo OCR; o sistema extrai número, CNPJ, objeto, valor mensal, vigência e acréscimos.
3. **Regras fixas** cruzam cada nota com o contrato do fornecedor:

| Regra | Gravidade |
|---|---|
| Fornecedor sem contrato | crítica |
| Valor acima do contratado (considera aditivos vigentes na data da nota e a tolerância configurada) | alta |
| Nota fora da vigência do contrato | alta |
| Nota possivelmente duplicada (mesmo número, mesmo prestador) | alta |
| Serviço diferente do objeto do contrato | média |
| Nota emitida para outro tomador | média |

4. A equipe **aprova** (com justificativa) ou **rejeita** cada divergência, e pode **avisar o fornecedor** com uma mensagem pronta para o e-mail cadastrado.
5. Tudo vira **planilha** (divergências, notas, fornecedores, decisões, avisos) e fica na **trilha de decisões**.

Cada empresa cliente é um espaço separado, com seus fornecedores (cadastrados à mão ou pelo CNPJ dos documentos), contratos e notas.

## Outros documentos fiscais (XML)

XML de **NF-e (modelo 55), NFC-e (65) e CT-e (57)** são lidos direto, sem OCR nem IA, cada um pelo seu leitor (`app/parser_nfe.py`, `app/parser_nfce.py`, `app/parser_cte.py`). O sistema guarda emitente, destinatário, itens, tributos, frete, pagamentos e notas referenciadas, avisa XML repetido e, se os esquemas oficiais (XSD) estiverem instalados, valida o leiaute. Esses documentos aparecem na tela **XML fiscais** e ficam fora da conferência nota × contrato, que é só para serviços. PDFs e fotos também ganham um **subtipo** (DANFE, DACTE, NFS-e…) pelos sinais do texto. Detalhes em [docs/PARSERS_FISCAIS.md](docs/PARSERS_FISCAIS.md).

## Integração com ERP

O ERP do cliente pode mandar documentos e buscar os resultados sem ninguém abrir a tela, pela API `/api/erp/v1` com chave de acesso (Bearer):

| Rota | O que faz |
|---|---|
| `POST /api/erp/v1/documents` | Envia até 20 arquivos; com `Idempotency-Key`, o mesmo pedido repetido não é processado duas vezes |
| `GET /api/erp/v1/documents` | Lista os envios da empresa |
| `GET /api/erp/v1/documents/{id}` | Situação e progresso de um envio |
| `GET /api/erp/v1/documents/{id}/results` | Documentos lidos, com tipo, confiança, valores e chave fiscal (sem texto livre nem nomes) |

O administrador cria, troca e revoga as chaves em `/api/integracoes`; cada uso fica numa auditoria que não pode ser alterada. Detalhes em [docs/ERP_API_V1.md](docs/ERP_API_V1.md).

## Resultado medido

Lote fictício gerado com gabarito: 8 fornecedores, **124 páginas num TIFF só de imagem** (contratos de 9 páginas, aditivos e notas misturados; ~6% das folhas tortas, borradas e apagadas) + 24 XML de NFS-e. Processado no notebook, sem a chave do Claude, em cerca de 5 minutos (OCR local, ~2 s por página).

| Medida | Resultado |
|---|---|
| Início e fim dos documentos (F1) | 97% |
| Documentos inteiros certos (páginas + tipo) | 88% |
| Páginas com o tipo certo | 93% |
| Enviados para revisão humana | 16% (as folhas ruins) |
| Acerto do que foi aprovado sem revisão | 100% |
| Notas com problema encontradas | 5 de 6, sem alarme falso (a 6ª esperava o contrato sair da revisão) |

Tudo o que o sistema errou foi para a revisão humana: nada errado foi aprovado sozinho. Os dados sintéticos são mais fáceis que documentos reais: os números servem para comparar versões e mostrar o fluxo, não como promessa de acerto. A tela **Acerto da IA** refaz essa medição com um lote novo.

## Como foi feito

- **Python + FastAPI**, banco **SQLite** com busca de texto (FTS5).
- Front em **React + Tailwind** (Vite), seguindo o Figma; a versão anterior das telas, em HTML/JS sem build, fica em `web/` até a migração terminar.
- **PyMuPDF** para PDF e imagens, **RapidOCR** para o OCR local, **Claude** (`claude-opus-5-5`) opcional para leitura multimodal.
- Fila de processamento própria, página a página, com ponto de retomada.
- Gerador de documentos fictícios com gabarito: `scripts/generate_synthetic_batch.py`.

```text
app/conciliacao.py  regras de conferência, decisões e medição contra o gabarito
app/fiscal.py       leitura do XML da NFS-e e dos campos de contratos, aditivos e notas
app/pipeline.py     fila: recebe, renderiza, lê e agrupa as páginas; retoma após falha
app/analise.py      tipo, início de documento e confiança (local ou Claude)
app/anonimizar.py   dados protegidos no texto e na imagem
app/parser_*.py     leitura do XML de NF-e, NFC-e e CT-e (roteador_fiscal.py escolhe o leitor)
app/classificacao_subtipos.py  subtipo do documento (DANFE, DACTE, NFS-e…) pelos sinais do texto
app/integrations/   API do ERP: chaves de acesso, envio, resultados e auditoria
frontend/           telas novas (React + Tailwind)
web/index.html      telas da versão anterior (Contratos, Configurações e Ajuda)
tests/              118 testes automáticos
```

O GitHub roda os testes e o build do front a cada commit (`.github/workflows/ci.yml`).

Testes:
- **Linux:** `.venv/bin/pytest tests -q`
- **Windows:** `.venv\Scripts\python.exe -m pytest tests -q`

## Time

| Pessoa | Principais entregas |
|---|---|
| Eduardo Noronha | Plataforma (separação, OCR, revisão humana, conferência nota × contrato), marca, layouts no Figma e o front novo em React (dashboard, envio, revisão, documento, busca, relatórios) |
| Leonardo Bernardo Maciel | Leitura de NF-e, NFC-e e CT-e, validação XSD, subtipos de documento, tela XML fiscais e o CI |
| Martha Machado Vieira | Integração com ERP: chaves de acesso, envio com idempotência, resultados e auditoria |
| Ruan Silva | Scanner pela câmera, `iniciar.sh` para Linux e o fluxo de branches do time |

Como o time trabalha (branches, PRs e testes): **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## Limites (o que este MVP ainda não é)

- **Validado com dados fictícios.** Próximo passo: piloto com documentos reais de um cliente.
- Login, banco SQLite e segurança são de demonstração, não de produção. Sem criptografia do banco nem política de retenção.
- Com o Claude ligado, as páginas vão para a API da Anthropic antes de serem anonimizadas; em produção isso exige contrato de tratamento de dados (LGPD).
- O XML de exemplo da NFS-e imita o leiaute nacional; falta validar com o XSD oficial e com notas reais. Para NF-e, NFC-e e CT-e a validação XSD existe, mas depende de instalar os esquemas oficiais, e o protocolo do XML não é uma consulta à SEFAZ.
- Leitura local leva cerca de 2 a 3 segundos por página digitalizada; lotes de milhares de páginas pedem mais de um processador trabalhando ao mesmo tempo.
- Os avisos ao fornecedor são gerados e registrados, mas o envio é feito pelo e-mail de quem revisa (não há servidor de e-mail).

## Próximos passos

- Buscar as notas automaticamente no Ambiente de Dados Nacional da NFS-e pelo CNPJ do tomador.
- Portal para o fornecedor enviar os próprios documentos.
- Conferir retenções (ISS, INSS) e boletins de medição.
