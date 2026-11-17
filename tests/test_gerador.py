import json
from pathlib import Path
import sys
import fitz
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from generate_synthetic_batch import synthetic_cnpj, cnpj_valid, generate


def test_valid_cnpjs():
    generated = [synthetic_cnpj(i) for i in range(1, 100)]
    assert len(set(generated)) == len(generated)
    assert all(cnpj_valid(n) for n in generated)
    assert not cnpj_valid('11.111.111/1111-11')


def test_small_generator(tmp_path):
    folder = tmp_path / 'demo'
    summary = generate(folder, supplier_count=3, invoices_per_supplier=3, seed=42, scan=False)
    truth = json.loads((folder/'ground_truth.json').read_text(encoding='utf-8'))
    assert summary['total_pages'] == 3*9+9*2+4
    assert summary['pdf_documents'] == 3+9+2
    assert len(truth['page_map']) == summary['total_pages']
    assert len(truth['boundary_start_pages']) == summary['pdf_documents']
    assert len(list((folder/'notas_xml').glob('*.xml'))) == 9
    assert {'VALOR_JUSTIFICADO_ADITIVO'} <= set(truth['expected_findings'][0]['reasons'])
    with fitz.open(folder/truth['batch_file']) as batch:
        assert batch.page_count == summary['total_pages']
        for doc in truth['documents']:
            assert doc['batch_end_page']-doc['batch_start_page']+1 == doc['pages']
            assert truth['page_map'][doc['batch_start_page']-1]['document_id'] == doc['document_id']


def test_deterministic(tmp_path):
    first = generate(tmp_path/'a', 3, 3, 123, False)
    second = generate(tmp_path/'b', 3, 3, 123, False)
    assert first == second
    a = json.loads((tmp_path/'a'/'ground_truth.json').read_text(encoding='utf-8'))
    b = json.loads((tmp_path/'b'/'ground_truth.json').read_text(encoding='utf-8'))
    assert a == b


def test_refuses_unmarked_directory(tmp_path):
    folder = tmp_path/'personal'
    folder.mkdir()
    (folder/'important.txt').write_text('KEEP')
    try:
        generate(folder, 3, 3)
    except FileExistsError:
        pass
    else:
        raise AssertionError('Expected FileExistsError')
    assert (folder/'important.txt').read_text() == 'KEEP'
