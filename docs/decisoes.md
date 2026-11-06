# Decisões técnicas — Fase 1

1. **Monólito modular:** uma API FastAPI e um worker Celery, sem microserviços internos.
2. **Offline por padrão:** LLM_API_KEY vazia; nenhuma chamada a modelos externos nesta fase.
3. **PostgreSQL + MinIO + Redis:** serviços separados para dados, objetos e filas.
4. **Autenticação demo:** três contas são criadas no início, com senhas no `.env`; não serve como autenticação corporativa ou SSO.
5. **Front mínimo:** login, lista e criação de lotes. Não existem upload, OCR, conciliação ou relatórios nesta fase.
6. **Armazenamento:** bucket privado criado automaticamente no início da API.
7. **JWT:** token em memória no frontend (não em localStorage), sem refresh token.
8. **PREMISSA regulatória:** referência à Resolução CGSN nº 191/2026 consta da proposta e depende de verificação jurídica antes da apresentação como conclusão normativa.
9. **PREMISSA fiscal:** futuro parser NFS-e XML terá mapa de campos configurável; não presume um layout definitivo.
10. **Escalabilidade e segurança:** infraestrutura destinada a demonstração local, não endurecida para produção.

## Fase 2 — Decisões e premissas
11. **Gerador isolado:** perfil `tools` no Docker Compose, sem exigir Python instalado no Windows.
12. **Gabarito determinístico:** seed configurável, com páginas de início/fim, documentos, campos e divergências esperadas.
13. **PREMISSA — XML:** XML é um formato demonstrativo próprio (`NfseDemonstracao`), **não** o XML oficial da NFS-e. Parser oficial será implementado na Fase 6.
14. **PREMISSA — CNPJ:** gerado com dígitos verificadores válidos; não é consultado em registro oficial e pode coincidir com identificador real. Não usar fora de testes.
15. **PDF digitalizado:** subconjunto rasterizado com inclinação leve/redução de contraste para testes de OCR; PDF combinado reúne documentos embaralhados por documento, preservando ordem interna das páginas.
16. **Scenarios:** aditivo válido, aditivo vencido, valor divergente, descrição diferente, nota fora da vigência, duplicação e nota de CNPJ sem contrato correspondente na base sintética.
17. **Infraestrutura:** imagem MinIO original indisponível no ambiente do usuário; alterada para `pgsty/silo` (compatibilidade S3 deve ser confirmada em teste local). Override `electron-to-chromium` aplicado devido a E404 observado no npm.
18. **Separadores e brancos:** não estão no PDF combinado desta fase; inclusão futura deve criar labels de `non_document_page` no gabarito.


### Fase 3 — limites do MVP
- Upload inicialmente pela API com limite de 40 MiB e 500 páginas por arquivo, sem multipart S3 pré-assinado.
- PDF com camada de texto é lido pelo PyMuPDF; caso contrário usa Tesseract português e inglês.
- Uma tarefa Celery por página; resultados e erros persistem no banco.
- Confiança `1.0` para PDF digital é sinalizador de texto nativo, não score de qualidade.
- Sem ZIP, XML, busca, revisão, exportação de PDF pesquisável ou reinício automático de tasks interrompidas nesta fase.
