# NFS-e de exemplo (fictícia)

`NFSe-exemplo-v1.01.xml` segue o leiaute nacional da NFS-e **v1.01** e foi validada contra os esquemas oficiais
(`NFSe-ESQUEMAS_XSD-v1.01-20260209`, publicados em gov.br/nfse → Documentação técnica → Documentação atual).

- Todos os dados são fictícios (CNPJ de teste com dígito verificador válido, município Garanhuns/PE).
- A assinatura digital é um marcador, não uma assinatura válida.
- O esquema oficial tem um defeito no campo `serie`: o padrão `^0{0,4}\d{1,5}$` usa `^` e `$`, que em XSD são
  caracteres literais, então nenhum valor real passa. Com esse padrão corrigido para `0{0,4}\d{1,5}`, o arquivo valida.

Para testar: arraste o XML em **Enviar documentos**. A nota aparece em **Notas fiscais** e é conferida contra o contrato.
