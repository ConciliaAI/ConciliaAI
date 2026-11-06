# Entrega técnica — MVP Essencial (Fases 4–7 simplificadas)

## Dependências e componentes

- Executa sobre a infraestrutura da Fase 3, **sem novos containers**.
- Banco: migração Alembic `0003_mvp_essential.py` cria `document_groups`, `findings`, `review_actions`.
- Backend: `intelligence.py` (motor puro), `mvp_service.py` (persistência), `mvp_api.py` (rotas), alterações em `main.py`.
- Frontend: nova interface React com documentos, revisão, divergências e busca OCR.
- Dados de demonstração: `demo/lote_demo_essencial.pdf` (14 páginas) + `gabarito_demo.json`.

## Fluxo operacional

`Upload → OCR → POST /analyze → grupos → campos → regras → revisão humana`.

1. `/start` enfileira OCR das páginas pelo Celery (Fase 3).
2. `/analyze` requer todas as páginas concluídas sem erro, processa cada arquivo separadamente.
3. `segment()` inicia grupo na primeira página e abre novo grupo com numeração reiniciada, identificação alterada ou mudança de tipo.
4. `classify()` atribui categoria e score heurístico. Confiança do grupo considera o menor score OCR das páginas.
5. `extract_fields()` identifica rótulos e guarda valor, página, trecho e confiança por campo.
6. `reconcile()` relaciona CNPJ/contrato e detecta valor diferente, vigência, duplicata ou serviço incompatível. Só trata aditivo como justificativa se houver vínculo, data aplicável e valor igual à diferença.
7. `/review`, `/split`, `/merge` atualizam grupos e registram ações. Revisões de alertas são protegidas contra recálculo destrutivo.

## Testes executados

- `pytest` isolado para `test_intelligence.py`: **5 passed** (sem `conftest.py`, que depende de `pwdlib` não disponível no ambiente da criação).
- `extract_page()` em 14 páginas: 2 via Tesseract, 12 extração direta de texto. **7 grupos corretos de 7 esperados** na amostra, sem inferir que essa taxa se reproduzirá em produção.
- `reconcile()` no lote: **1 aditivo justificável, 2 diferenças não justificadas**. As 3 evidências foram obtidas dos textos OCR/PDF do lote.
- SQLAlchemy em SQLite temporário: grupo/documento e divergência persistidos (7/3); reanálise rejeitada para preservar revisão.
- Compilação Python: aprovada.

## Testes pendentes no ambiente Docker

- `docker compose up --build -d` e migração Alembic 0003 em PostgreSQL.
- `docker compose exec api pytest -q` com dependências totais.
- `docker compose exec api ruff check .`.
- Build Vite e interações de interface.
- Concorrência/Celery para lotes maiores e 304 páginas.
- Validação com PDF/imagens heterogêneos de terceiros (autorizados).

## Restrição de escopo

As regras e os rótulos reconhecidos foram definidos para o **conjunto sintético do projeto**, não para todos os documentos reais. Não há XML NFS-e oficial, leitura de código de barras, separação de páginas não contíguas, PDF pesquisável com camada textual, análise por LLM, anonimização, relatórios nem métricas corporativas. A classificação e as decisões são **auxiliares e revisáveis**.

## Operação segura

- Não enviar `.env` ao GitHub.
- Não usar `docker compose down -v`.
- Criar novo lote para repetir a demonstração: uma nova análise do mesmo lote é bloqueada para não apagar decisões.
- Revisão exige `admin` ou `revisor`.
