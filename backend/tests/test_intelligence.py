from app.intelligence import classify, segment, extract_fields, reconcile


def page(number, text, confidence=0.99):
    return {'number':number, 'text':text, 'confidence':confidence}

C = '''CONTRATO DE PRESTACAO DE SERVICOS
Instrumento: CTR-001
Contratada: Empresa Sintetica
CNPJ contratada: 87.000.001/1001-78
CNPJ contratante: 87.000.999/1999-99
Objeto: Limpeza e conservacao
Valor mensal: R$ 8.000,00
Vigencia: 01/01/2026 a 31/12/2026'''
A = '''TERMO ADITIVO CONTRATUAL
Aditivo: ADT-001
Contrato: CTR-001
Fornecedor: 87.000.001/1001-78
Acrescimo mensal: R$ 2.500,00
Vigencia do aditivo: 2026-08-01 ate 2026-12-31'''
N = '''NOTA FISCAL DE SERVICOS - DEMONSTRACAO
Numero: 30000
CNPJ prestador: 87.000.001/1001-78
CNPJ tomador: 87.000.999/1999-99
Data emissao: 2026-08-01
Descricao: Limpeza e conservacao
Valor do servico: R$ 10.500,00
Contrato referenciado: CTR-001'''


def test_segmentation_handles_repeated_heading():
    pages=[page(1,C+'\nPagina 1 de 2'),page(2,C+'\nPagina 2 de 2'),page(3,N+'\nPagina 1 de 2'),page(4,N+'\nPagina 2 de 2'),page(5,A+'\nPagina 1 de 1')]
    grouped=segment(pages)
    assert [(g.start,g.end,g.kind) for g in grouped]==[(1,2,'contrato'),(3,4,'nota_fiscal_servico'),(5,5,'aditivo_contratual')]


def test_extraction_and_justified_discrepancy():
    docs=[{'id':i,'kind':kind,'fields':extract_fields([page(1,txt)],kind)} for i,(kind,txt) in enumerate([('contrato',C),('nota_fiscal_servico',N),('aditivo_contratual',A)],1)]
    findings=reconcile(docs)
    assert len(findings)==1
    assert findings[0]['rule']=='R02_ADITIVO'
    assert findings[0]['status']=='justificada_pendente_validacao'
    assert len(findings[0]['evidence'])==3


def test_unjustified_and_out_of_period():
    notes=N.replace('2026-08-01','2027-02-01')
    docs=[{'id':1,'kind':'contrato','fields':extract_fields([page(1,C)],'contrato')},{'id':2,'kind':'nota_fiscal_servico','fields':extract_fields([page(1,notes)],'nota_fiscal_servico')},{'id':3,'kind':'aditivo_contratual','fields':extract_fields([page(1,A)],'aditivo_contratual')}]
    rules={f['rule'] for f in reconcile(docs)}
    assert {'R02_VALOR','R05_FORA_VIGENCIA'}<=rules


def test_no_contract_and_ambiguity():
    inv={'id':3,'kind':'nota_fiscal_servico','fields':extract_fields([page(1,N.replace('87.000.001/1001-78','12.345.678/0001-90'))],'nota_fiscal_servico')}
    assert reconcile([inv])[0]['rule']=='SEM_CONTRATO'
    assert classify('bloco sem caracteristicas')[0]=='outros'


def test_blank_page_is_low_confidence():
    groups=segment([page(1,'',0),page(2,'',0)])
    assert len(groups)==1 and groups[0].confidence<=.1
