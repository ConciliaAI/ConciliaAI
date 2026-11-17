# Parsers fiscais XML da Concilia AI — NF-e 55, NFC-e 65 e CT-e 57

## Finalidade

A Concilia AI já identifica imagens e PDFs pelo OCR. Os novos parsers lêem XML estruturado **sem OCR ou IA**. O roteamento é exclusivo por `infNFe/ide/mod` (55 ou 65) e `infCte/ide/mod` (57); a NFS-e permanece no parser `app/fiscal.py` e na tabela `notas`.

Os XMLs NF-e, NFC-e e CT-e ficam na tabela **documentos_fiscais**, e não são incluídos na conciliação atual de contratos de prestação de serviços; evitamos associar indevidamente NF-e de mercadoria a serviços.

## Interfaces

1. Na aplicação, escolha **Enviar documentos**, selecione um XML (ou ZIP contendo XMLs fiscais).
2. Após o processamento, abra a opção **XML fiscais** no menu lateral.
3. Filtre por modelo e abra os detalhes: emitente, destinatário, itens, tributos, fretes, pagamentos, CT-e e notas referenciadas.
4. A API disponibiliza `GET /api/ws/{ws}/documentos-fiscais?modelo=55` (ou 65, 57) e `GET /api/documentos-fiscais/{id}`; `GET /api/envios/{eid}` inclui `fiscais`.
5. Os registros têm hash SHA-256, número, modelo, leiaute, protocolo presente no XML, valores em decimal textual, campos e rastreabilidade por caminho XML. XML original permanece na pasta de envios local.

## Validação de leiaute XSD (opcional, pacote oficial externo)

Os leiautes fiscais possuem versões e Notas Técnicas específicas. O parser extrai informações mesmo sem XSD, mas **não declara o documento validado** se o pacote oficial correspondente não estiver disponível. Para habilitar validação, obtenha os esquemas pertinentes à versão do XML diretamente dos portais oficiais:

- NF-e/NFC-e: https://www.nfe.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=BMPFMBoln3w=
- CT-e: https://www.cte.fazenda.gov.br/portal/listaConteudo.aspx?tipoConteudo=0xlG1bdBass=

Descompacte o pacote completo, preservando os XSDs referenciados pelos includes. Configure no arquivo `.env`:

```ini
CONCILIA_XSD_DIR=C:\\caminho\\para\\pacote-xsd
```

Os nomes esperados para versões 4.00 incluem `nfe_v4.00.xsd` / `procNFe_v4.00.xsd` e `cte_v4.00.xsd` / `procCTe_v4.00.xsd`, conforme a raiz do XML. A pasta e os esquemas devem corresponder à atualização normativa do documento; se um esquema não existir, o resultado será `nao_executada`, nunca `aprovada`. Quando disponível, a validação usa `lxml.etree.XMLSchema` sem acesso à rede.

**Validação estrutural não comprova autenticidade.** O protocolo `cStat=100` ou `150` recebido no XML é exibido como informação documental, mas **não é consulta à SEFAZ**, não comprova assinatura digital nem garante que o documento não foi cancelado. Assinatura, situação atual, eventos e autorização online precisarão de integração fiscal própria.

## Formato de dados

```json
{
  "modelo": "55",
  "tipo": "nfe",
  "versao": "4.00",
  "campos": {"numero": "123", "emitente": {}, "destinatario": {}, "valor_total": "20.00"},
  "itens": [{"numero_item": "1", "ncm": "12345678", "cfop": "5102", "impostos": {}}],
  "referencias": [],
  "proveniencia": {"numero": {"caminho_xml": "//NFe/infNFe/ide/nNF", "valor_original": "123"}},
  "protocolo": {"codigo": "100", "autorizado": true, "verificado_na_sefaz": false},
  "validacao": {"xml_bem_formado": true, "xsd": "nao_executada", "autorizacao_online": "nao_consultada"}
}
```

Os valores decimais XML são guardados como strings para não introduzir erros por ponto flutuante. Atributos, elementos repetidos e novos grupos tributários são preservados nos subgrupos correspondentes.

## Limitações e próximos passos

- O parser reconhece o grupo principal dos modelos 55, 65 e 57; variantes especiais, eventos, cancelamentos, cartas de correção, inutilizações, manifestações e outros documentos DF-e não são convertidos automaticamente em notas.
- A validação XSD é opcional e depende dos esquemas oficiais locais da **versão exata**, inclusive os respectivos includes.
- Sem consulta oficial e verificação de assinatura XML, nenhum resultado deve ser rotulado como autenticidade fiscal confirmada.
- Testes unitários sintéticos e API não substituem testes com XMLs reais anonimizados, modelos anteriores, várias NTs, contingência e múltiplos grupos tributários.
- O suporte a PDFs e imagens de DANFE/DACTE continua no OCR e classificador; isto **não** transforma um PDF em XML fiscal completo.

## Verificação local

```powershell
python -m pytest tests/test_parsers_fiscais.py -v
python -m pytest tests -q
cd frontend
npm ci
npm run build
```

Use arquivos XML válidos de teste, evitando dados fiscais reais durante a homologação.
