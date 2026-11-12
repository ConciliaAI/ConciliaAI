# Concilia AI

**Hack Garanhuns Tech 2026 · Desafio 3 — Document AI Factory (desafio proposto pela Bernhoeft)**

A Concilia AI recebe lotes grandes de documentos digitalizados e misturados, descobre onde cada documento começa e termina, agrupa as páginas, classifica o tipo, deixa o texto pesquisável (OCR) e manda para revisão humana o que não tem certeza. O foco é o documento que mais pesa na gestão de terceiros: a **nota fiscal de serviço (NFS-e)**, conferida contra o contrato do fornecedor.

> Ferramenta de apoio à conferência documental. Aponta diferenças e mostra de onde elas vêm; não substitui análise jurídica, contábil ou tributária.

## O problema

Grandes empresas contratam dezenas de micro e pequenas empresas. Cada uma manda contratos, aditivos e notas fiscais, muitas vezes digitalizados, fora de ordem e num arquivo só. Alguém precisa separar, ler e conferir se o que foi cobrado bate com o que foi contratado. Desde 01/11/2026 (Resolução CGSN nº 191/2026, premissa da proposta), MEI e empresas do Simples emitem NFS-e só pelo Emissor Nacional: o XML padronizado facilita a conferência automática.

## Como abrir

- **Linux:** Execute `./iniciar.sh` no terminal (veja o [Protocolo detalhado para Linux](docs/PROTOCOLO_LINUX.md)).
- **Windows:** Dê dois cliques em **`iniciar.bat`**.

Na primeira vez ele instala tudo automaticamente (precisa de internet e Python 3.11+). O navegador abre em http://127.0.0.1:8000.

| Usuário | Senha | Pode |
|---|---|---|
| admin | admin123 | tudo: clientes, configurações, avaliação |
| revisor | revisor123 | decidir dúvidas e divergências, avisar fornecedores, ver dados protegidos |
| operador | operador123 | enviar documentos e consultar |

Roteiro da demonstração em **[LEIA-ME.md](LEIA-ME.md)**.

### Front novo (React + Tailwind), em construção

As telas estão sendo refeitas em `frontend/` (Vite, React, Tailwind, JavaScript), seguindo os layouts do Figma. Ele usa a mesma API da plataforma, então abra a plataforma primeiro (porta 8000) e depois:

```bash
cd frontend
npm install
npm run dev
```

Abre em http://localhost:5173.

| Tela | O que faz |
|---|---|
| Login | Entrada com o painel da marca e a prévia do dashboard |
| Documentos (dashboard) | Bloco do scanner logo no topo, números do lote, pastas por tipo, tabela com filtro e exclusão, fila "Precisam de você" |
| Enviar documentos | Arrastar o lote, progresso página a página com miniaturas, pausar, retomar e cancelar, histórico com o resultado de cada envio |
| Revisão humana | Uma fila só com as dúvidas da leitura e as divergências nota × contrato; páginas lado a lado, respostas com atalhos 1, 2 e 3 |
| Documento | Página do documento, divergência com os valores, confiança da leitura e campos lidos; aprovar, rejeitar, baixar PDF e excluir |
| Busca | Busca no texto de todos os documentos, com os dados protegidos mascarados |

Contratos, Relatórios, Configurações e Ajuda ainda abrem na versão atual, em http://127.0.0.1:8000. A interface escala junto com a largura e a altura da janela, mantendo as proporções do Figma (1440 px).

O scanner é feito por outra pessoa do time: o botão "Escanear agora" já existe no dashboard (`frontend/src/components/BlocoScanner.jsx`, propriedade `aoEscanear`) e é ali que ele se liga.

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

- **Python + FastAPI**, telas em HTML/JS sem build, banco **SQLite** com busca de texto (FTS5).
- **PyMuPDF** para PDF e imagens, **RapidOCR** para o OCR local, **Claude** (`claude-opus-5-5`) opcional para leitura multimodal.
- Fila de processamento própria, página a página, com ponto de retomada.
- Gerador de documentos fictícios com gabarito: `scripts/generate_synthetic_batch.py`.

```text
app/conciliacao.py  regras de conferência, decisões e medição contra o gabarito
app/fiscal.py       leitura do XML da NFS-e e dos campos de contratos, aditivos e notas
app/pipeline.py     fila: recebe, renderiza, lê e agrupa as páginas; retoma após falha
app/analise.py      tipo, início de documento e confiança (local ou Claude)
app/anonimizar.py   dados protegidos no texto e na imagem
web/index.html      as telas
tests/              28 testes automáticos
```

Testes:
- **Linux:** `.venv/bin/pytest tests -q`
- **Windows:** `.venv\Scripts\python.exe -m pytest tests -q`

## Limites (o que este MVP ainda não é)

- **Validado com dados fictícios.** Próximo passo: piloto com documentos reais de um cliente.
- Login, banco SQLite e segurança são de demonstração, não de produção. Sem criptografia do banco nem política de retenção.
- Com o Claude ligado, as páginas vão para a API da Anthropic antes de serem anonimizadas; em produção isso exige contrato de tratamento de dados (LGPD).
- O XML de exemplo imita o leiaute nacional; falta validar com o XSD oficial e com notas reais.
- Leitura local leva cerca de 2 a 3 segundos por página digitalizada; lotes de milhares de páginas pedem mais de um processador trabalhando ao mesmo tempo.
- Os avisos ao fornecedor são gerados e registrados, mas o envio é feito pelo e-mail de quem revisa (não há servidor de e-mail).

## Próximos passos

- Buscar as notas automaticamente no Ambiente de Dados Nacional da NFS-e pelo CNPJ do tomador.
- Portal para o fornecedor enviar os próprios documentos.
- Conferir retenções (ISS, INSS) e boletins de medição.
