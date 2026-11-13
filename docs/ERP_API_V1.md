# ERP API v1 — contrato de acesso e recuperação (PR #12)

## Escopo do acesso

As credenciais ERP são associadas a um **workspace** no cadastro. O workspace não é aceito do corpo, da query ou da rota ERP. Uma credencial com `documents:write` envia documentos para esse workspace; `results:read` consulta **todos os envios do mesmo workspace**, inclusive envios realizados pela interface ou por outras integrações. Não existe restrição por credencial de origem. É uma decisão explícita desta versão; revogar `results:read` se uma integração não deve ter visibilidade de todos os envios da empresa.

Consultas a outros workspaces retornam 404. O ID de `documents/{envio_id}` é do **envio/lote**, não de documento individual.

## Dados expostos

Respostas de listagem e detalhe incluem metadados técnicos e operacionais: ID, timestamps, estado, totais, progresso e códigos de erro controlados. A rota `results` inclui IDs, tipo, confiança, páginas, status, valores monetários, modelo fiscal, número, chave de acesso fiscal e data de emissão. Não inclui XML original, OCR integral, caminhos internos, CPF em campo específico, nome original do arquivo, origem livre, nomes de pessoas/empresas nem descrição textual livre.

A chave de acesso fiscal pode conter CNPJ e deve ser tratada como dado empresarial protegido pelo controle de workspace. Para casos de uso que exijam nomes/descrições, criar versão com permissões granulares, minimização e anonimização apropriadas; não acrescentar campos sensíveis silenciosamente ao contrato v1.

Os endpoints exigem TLS na implantação e não substituem política de retenção de dados e acesso aos resultados.

## Idempotência e recuperação

`Idempotency-Key` identifica um pedido por integração. Cada execução nova recebe `tentativa_id` UUID no banco; o vínculo do envio, a conclusão e o registro de falha exigem a mesma identidade. Uma execução antiga não pode vincular o envio a uma reserva recriada com a mesma chave.

A API de desbloqueio **rejeita** reservas em `processando`, mesmo com confirmação administrativa. Uma reserva `indeterminado` somente pode ser desbloqueada quando não há envio associado. Reservas com envio associado devem ser reconciliadas, sem desbloqueio automático.

Após queda/reinicialização, `processando` pode permanecer bloqueada: não existe detecção distribuída confiável da morte de um worker nem rotina automática de expiração. A recuperação desse estado requer procedimento operacional futuro, com garantia externa de que a tentativa antiga terminou, e transição auditada para `indeterminado`. Não edite o SQLite manualmente sem backup e revisão técnica.

O processamento do pipeline (arquivos, OCR, fila, banco) **não é atômico ponta a ponta**. O vínculo da reserva ao ID de envio é confirmado na mesma transação SQLite da criação do envio, mas falhas posteriores exigem inspeção.

## Limites

Até 20 arquivos por pedido ERP e até `CONCILIA_MAX_MB` MiB por arquivo e por requisição no total (padrão 300). O endpoint carrega os bytes em memória e ainda não oferece upload retomável. Não o exponha a grandes uploads simultâneos sem controle de infraestrutura.

## Verificação

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_erp_endpoints.py
.\.venv\Scripts\python.exe -m pytest -q tests
cd frontend
npm ci
npm run build
```
