# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Empresas de BPO (financeiro, fiscal e de gestão de terceiros) e escritórios contábeis. Quem usa é o analista que recebe lotes de notas fiscais, contratos, aditivos e comprovantes de vários clientes, misturados e escaneados, e confere tudo à mão. Quem compra é o gestor do BPO, que quer processar mais volume com a mesma equipe. *(Inferido da conversa; o time ainda confirma o público.)*

## Product Purpose
A Concilia AI recebe lotes grandes de documentos (XML da NFS-e, PDF, TIFF escaneado, foto, ZIP), descobre onde cada documento começa e termina, classifica o tipo, deixa o texto pesquisável (OCR) e confere cada nota fiscal contra o contrato e os aditivos do fornecedor. O que tem dúvida vai para revisão humana, com o motivo. Sucesso: o BPO confere notas em escala sem digitar nada, e nada errado passa aprovado sozinho.

## Positioning
Não é só OCR: separa o lote, entende o documento e cruza nota × contrato (valor com aditivos vigentes, vigência, duplicidade, serviço e tomador), mostrando de onde vem cada diferença.

## Capabilities and Constraints
- SaaS próprio, sem integração obrigatória com outro sistema. Uma conta por empresa, sem workspaces (ver decisões abaixo).
- Origem: desafio proposto pela Bernhoeft no Hack Garanhuns Tech 2026; a Bernhoeft é cliente-alvo, não dona do produto.
- Planos propostos (a validar): Teste grátis (14 dias, 200 documentos), Essencial R$ 197/mês (até 100.000 documentos), Profissional R$ 497/mês (acima de 100.000 documentos, com integração com ERP).
- Cobrança real, app de celular e integração com ERP ainda não existem.

### Decisões da reunião (novembro de 2026)
- **Sem workspaces:** a pessoa cria a conta e já entra na plataforma. Não há "um espaço por cliente".
- **Sem cadastro de fornecedores:** a plataforma só lê e estrutura os dados do documento.
- **Limite:** base de 100.000 documentos.
- **Scanner logo de cara no dashboard,** para ler a nota que a pessoa tem na mão. Quem faz o scanner é outra pessoa do time.
- **Próximas frentes, quase todas no back-end:** relatório; identificação; mais formatos de documento; classificar e relacionar documentos; treinamento (base de referência para diferenciar e comparar); receber dados não estruturados e estruturar; dashboard de visualização; integração com ERP.
- Os layouts novos estão no Figma "Concilia AI - Landing", página "Plataforma v2 · ajustes da reunião". A Page 1 guarda a versão anterior.

## Brand Commitments
Nome "Concilia AI", logo "concilia.ai" com símbolo de duas folhas e check (pasta `marca/`, ver `marca/LEIA-ME.md`). Cores: Noite #0F1E3D, Confere #2F6BFF, Atenção #F5B700 (só alertas), Névoa #E9EFFD. Fontes escolhidas pelo usuário: Plus Jakarta Sans (títulos) e Inter (texto). Tom direto e concreto, em português.

## Evidence on Hand
Medido num lote de teste fictício de 124 páginas escaneadas com gabarito: 97% de acerto no início e fim dos documentos, 100% de acerto no que foi aprovado sem revisão, cerca de 2 s por página, 5 de 6 notas com problema encontradas sem alarme falso. Não há clientes, depoimentos nem logos de clientes: não inventar.

## Product Principles
- Mostrar o porquê de cada decisão da IA.
- Na dúvida, a IA pergunta a uma pessoa em vez de errar.
- Números medidos, não prometidos.
