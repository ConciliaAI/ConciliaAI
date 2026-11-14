# Como o time trabalha

## Branches

| Branch | Para que serve |
|---|---|
| `main` | A versão que funciona. Só recebe o que passou nos testes do `stage` |
| `stage` | Testes. A pessoa responsável pelos testes confere aqui antes de liberar para o `main` |
| `develop` | Desenvolvimento. Tudo o que fica pronto entra aqui primeiro |
| `feature/nome-da-tarefa` | Uma tarefa por branch, por exemplo `feature/scanner` ou `feature/tela-relatorios` |

Não usamos branch de hotfix: uma correção também é uma `feature/`.

## Passo a passo

1. Atualize o `develop` e crie o seu branch a partir dele:
   ```bash
   git checkout develop
   git pull
   git checkout -b feature/nome-da-tarefa
   ```
2. Trabalhe e faça commits pequenos, ao longo do caminho (veja as mensagens abaixo).
3. Antes de subir, rode os testes e o build do front:
   ```bash
   .venv\Scripts\python.exe -m pytest -q tests      # Windows
   .venv/bin/pytest -q tests                        # Linux
   cd frontend && npm run build
   ```
4. Envie o branch e abra um **PR para o `develop`**:
   ```bash
   git push -u origin feature/nome-da-tarefa
   ```
5. Outra pessoa do time revisa e aprova. O GitHub roda os testes e o build sozinho em cada PR (CI).
6. Com o `develop` funcionando, abre-se um **PR `develop` → `stage`**. A pessoa dos testes confere no `stage`.
7. Aprovado nos testes: **PR `stage` → `main`**. Se algo falhar, a correção volta pelo `develop` e o caminho se repete.

Se o `develop` andou enquanto você trabalhava e o PR mostrar conflito, traga o `develop` para o seu branch (`git merge origin/develop`), resolva o conflito, rode os testes de novo e envie.

## Mensagens de commit

A banca avalia o histórico do repositório, então cada commit precisa dizer o que mudou:

```text
tipo(área): o que mudou, em português

Por que mudou, se não for óbvio.
```

| Tipo | Quando |
|---|---|
| `feat` | Algo novo (tela, rota, leitor de documento) |
| `fix` | Correção |
| `test` | Testes |
| `docs` | README e documentação |
| `chore` | Organização, dependências, configuração |

Exemplos do próprio repositório: `feat(front): tela Relatórios igual ao Figma`, `fix: nao confunde referencia infNFe dentro de CTe com NF-e principal`.

## Antes de abrir o PR

- [ ] Os testes passam e o build do front não dá erro
- [ ] O commit é feito com a sua conta do GitHub (`git config user.name` e `user.email`)
- [ ] Nada de senha, chave ou arquivo `.env` no commit
- [ ] Se mudou algo que aparece para quem usa, o README foi atualizado
