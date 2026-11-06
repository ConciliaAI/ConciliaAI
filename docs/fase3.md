# Fase 3 — Ingestão e OCR

## Entregas

- `POST /batches/{id}/upload`: PDF, PNG/JPEG, TIFF (até 40 MiB e 500 páginas por arquivo).
- `POST /batches/{id}/start`: publicação de uma tarefa Celery por página.
- `GET /batches/{id}/progress`: contagem de páginas e percentual, para polling a cada 2,5 s.
- `GET /batches/{id}/pages`: texto, confiança estimada, método e caixas das palavras.
- Originais armazenados no S3 compatível, metadados no PostgreSQL.
- Texto digital via PyMuPDF; páginas sem texto via Tesseract `por+eng`.

## Teste manual

1. `docker compose up --build -d`
2. Acesse `http://localhost:5173` e autentique-se.
3. Crie lote, envie PDF da Fase 2 (primeiro um pequeno PDF) e clique **Iniciar processamento**.
4. Acompanhe a barra e abra o texto de uma página.
5. Para checar tarefas: `docker compose logs --tail 100 worker`.
6. Para testes: `docker compose exec api pytest -q`.

## Limites deliberados

- Não há separação dos documentos dentro do PDF (Fase 4).
- Sem classificação nem revisão humana (Fase 5).
- Sem parser XML, ZIP ou NFS-e nesta etapa (Fase 6).
- Não produz ainda um PDF com camada de texto pesquisável; texto OCR está pesquisável **via API** e armazenado por página, mas a busca full-text e o PDF derivado ficam pendentes.
- Processamento de página não retomará automaticamente se o worker morrer após assumir a página; recuperação idempotente será acrescentada na Fase 9.
- A confiança do texto nativo `1.0` indica apenas origem digital, não acurácia validada.
- O cálculo de progresso usa polling, sem ETA preditivo.
- Para o MVP, cada tarefa baixa o arquivo inteiro do armazenamento para extrair uma única página; ainda há margem de otimização.
- Arquivos que falharem podem ser inspecionados pelos erros por página, mas a retentativa automática ficou fora da fase.
- Não enviar documentos reais, pois não houve auditoria de segurança.
