from io import BytesIO
import fitz
from app import main


def headers(client):
    response = client.post('/auth/token', data={'username': 'teste', 'password': 'senha-forte'})
    return {'Authorization': 'Bearer ' + response.json()['access_token']}


def test_health(client):
    assert client.get('/health').json()['phase'] == 3


def test_auth_and_batch(client):
    assert client.get('/batches').status_code == 401
    assert client.post('/auth/token', data={'username': 'teste', 'password': 'errada'}).status_code == 401
    h = headers(client)
    assert client.get('/auth/me', headers=h).json()['role'] == 'operador'
    created = client.post('/batches', headers=h)
    assert created.status_code == 201
    assert created.json()['status'] == 'created'
    assert len(client.get('/batches', headers=h).json()) == 1


def test_upload_progress_and_enqueue(client, monkeypatch):
    h = headers(client)
    batch_id = client.post('/batches', headers=h).json()['id']
    monkeypatch.setattr(main, 'upload_stream', lambda *args: None)
    sent = []
    monkeypatch.setattr(main.process_page, 'delay', lambda page_id: sent.append(page_id))
    doc = fitz.open()
    doc.new_page().insert_text((50, 50), 'Um contrato de demonstracao para testar OCR')
    raw = doc.tobytes()
    doc.close()
    response = client.post(f'/batches/{batch_id}/upload', headers=h,
        files={'file': ('contrato.pdf', raw, 'application/pdf')})
    assert response.status_code == 201, response.text
    assert response.json()['total_pages'] == 1
    assert client.get(f'/batches/{batch_id}/progress', headers=h).json()['pages_total'] == 1
    queued = client.post(f'/batches/{batch_id}/start', headers=h)
    assert queued.status_code == 200
    assert len(sent) == 1
    assert client.get(f'/batches/{batch_id}/pages', headers=h).json()[0]['status'] == 'pending'


def test_reject_invalid_and_unauthorized(client, monkeypatch):
    h = headers(client)
    batch = client.post('/batches', headers=h).json()['id']
    assert client.post(f'/batches/{batch}/upload',
        files={'file': ('x.pdf', b'bad', 'application/pdf')}).status_code == 401
    assert client.post(f'/batches/{batch}/upload', headers=h,
        files={'file': ('x.exe', b'bad', 'application/octet-stream')}).status_code == 415
    assert client.post(f'/batches/{batch}/upload', headers=h,
        files={'file': ('x.pdf', b'bad', 'application/pdf')}).status_code == 422
