# Demonstração curta do MVP Essencial

`lote_demo_essencial.pdf` é um lote sintético com contratos, notas e aditivo misturados.
A ordem de documentos (cada um com 2 páginas) inclui um caso de aditivo aplicável,
um caso de diferença sem justificativa e um caso de aditivo fora de período.

## Procedimento

1. Inicie o projeto com `docker compose up --build -d`.
2. Acesse http://localhost:5173, autentique-se com `admin`.
3. Crie lote; envie `demo/lote_demo_essencial.pdf`.
4. Clique **Iniciar OCR** e confira o progresso até 100%.
5. Clique **Separar e conciliar**.
6. Verifique os agrupamentos, confiança, pendências e alertas com evidências.
7. Busque `30000`, corrija um tipo com justificativa e teste a revisão.

Os documentos de teste são didáticos e sem validade fiscal. Não confundir os scores
heurísticos com probabilidades calibradas. A validação desta amostra não prova
capacidade de produção com arquivos fiscais reais.
