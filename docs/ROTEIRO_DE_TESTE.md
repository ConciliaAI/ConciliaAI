# Roteiro de teste da plataforma

Para quem vai testar no `stage` antes de liberar para o `main`. Leva uns 15 minutos.

## 1. Abrir

1. Pegue a versão mais nova: `git pull`
2. Dê dois cliques no **`iniciar.bat`** (no Linux: `./iniciar.sh`).
   - Ele instala ou atualiza o que faltar e monta as telas sozinho. Na primeira vez demora uns minutos; depois, segundos.
   - Precisa de **Python 3.11+** e, para as telas novas, **Node.js LTS** (nodejs.org). Sem Node, abre a versão anterior das telas.
3. O navegador abre em **http://127.0.0.1:8000**. Deixe a janela preta aberta enquanto usa.

Só isso: não precisa de `npm run dev`, de segundo terminal nem de aceitar certificado.

**Banco:** sem `DATABASE_URL` no `.env`, tudo fica num SQLite só seu. Com as linhas do Supabase (peça no privado), você vê os mesmos dados do time. Veja `docs/SUPABASE.md`.

**Scanner no celular:** a câmera do celular exige https. Só para esse teste, rode `cd frontend` e `npm run dev`, abra no celular o endereço "Network" que aparecer e aceite o aviso de certificado (é de teste).

## 2. Testar

| # | Faça | Deve acontecer |
|---|---|---|
| 1 | Entre com `admin` e a senha do seu `.env` (sem `.env`: `admin123`) | Abre o dashboard, com o seletor de cliente no topo |
| 2 | Saia e clique em **Criar conta**; crie uma empresa | Cai em "Crie o primeiro workspace" |
| 3 | Crie dois workspaces e troque entre eles no seletor | Cada um começa vazio; nenhum cliente da demonstração aparece |
| 4 | Volte para `admin`. Em **Enviar documentos**, envie um PDF ou o lote de exemplo | O progresso aparece página a página |
| 5 | Espere terminar | Documentos no dashboard, pastas por tipo, números do lote |
| 6 | Abra **Revisão humana** e responda um item (atalhos 1, 2, 3) | O item sai da fila (se era uma nota, pode virar uma divergência: é a conferência funcionando) |
| 7 | Clique num documento da tabela | Página do documento, campos lidos, baixar PDF |
| 8 | Busque uma palavra na barra do topo | Resultados com o trecho destacado e CPF mascarado |
| 9 | **Contratos** | Contratos lidos, vigência, aditivos ao clicar |
| 10 | **Relatórios**, troque o mês, baixe uma planilha | Gráficos mudam; o CSV abre no Excel |
| 11 | **XML fiscais** (envie um XML de NF-e, NFC-e ou CT-e antes) | Lista por modelo e detalhes da nota |
| 12 | **Configurações**: passe pelas abas; crie um usuário e uma chave de ERP | Usuário criado; a chave aparece uma vez só; revogar funciona |
| 13 | Entre como `operador` e abra Configurações | Tudo visível, nada editável |
| 14 | **Ajuda** | Passo a passo e perguntas frequentes |
| 15 | No celular (veja "Scanner no celular" acima), use **Escanear agora** | A câmera abre e a foto vira documento |

## 3. Se der erro

Anote **a tela**, **o que você fez** e **a mensagem** (print ajuda; nada de senha ou chave no print) e abra uma issue ou mande no grupo. Erros aparecem na janela preta do `iniciar.bat`.

## Tempo de leitura

Página digitalizada passa por OCR local: cerca de 2 segundos por página no notebook (o lote de exemplo, com 109 páginas, leva uns 4 minutos). PDF com texto e XML são lidos quase na hora. Para a apresentação, deixe um lote já processado.
