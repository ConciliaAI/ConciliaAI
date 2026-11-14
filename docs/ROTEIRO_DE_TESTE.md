# Roteiro de teste da plataforma

Para quem vai testar no `stage` antes de liberar para o `main`. Leva uns 15 minutos.

## 1. Abrir

1. Atualize o branch e instale o que for novo:
   ```bash
   git pull
   .venv\Scripts\python.exe -m pip install -r requirements.txt     # Windows
   cd frontend && npm install
   ```
2. Ligue a plataforma (API): `iniciar.bat` (Windows) ou `./iniciar.sh` (Linux). Deixe a janela aberta.
3. Em outro terminal, o front: `cd frontend` e `npm run dev`.
4. Abra **https://localhost:5173** (com **s**).

**Aviso de certificado é normal.** O front usa um certificado de teste (para a câmera do scanner funcionar no celular). Na primeira vez, e sempre que reinstalar o front, o navegador mostra "Sua conexão não é particular": clique em **Avançado → Continuar para localhost**.

**Banco:** sem `DATABASE_URL` no `.env`, tudo fica num SQLite só seu. Com as linhas do Supabase (peça no privado), você vê os mesmos dados do time. Veja `docs/SUPABASE.md`.

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
| 15 | No celular (mesmo Wi-Fi), abra o endereço "Network" do `npm run dev` e use **Escanear agora** | A câmera abre e a foto vira documento |

## 3. Se der erro

Anote **a tela**, **o que você fez** e **a mensagem** (print ajuda; nada de senha ou chave no print) e abra uma issue ou mande no grupo. Erros da API aparecem na janela do `iniciar.bat`.

## Tempo de leitura

Página digitalizada passa por OCR local: cerca de 2 segundos por página no notebook (o lote de exemplo, com 109 páginas, leva uns 4 minutos). PDF com texto e XML são lidos quase na hora. Para a apresentação, deixe um lote já processado.
