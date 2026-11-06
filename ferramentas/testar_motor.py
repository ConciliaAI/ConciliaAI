"""Teste de ponta a ponta: envia o lote de exemplo, espera processar e mostra o resultado."""
import json
import sys
import time
import urllib.request
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
EX = Path(__file__).resolve().parent.parent / "exemplos"


def get(caminho):
    with urllib.request.urlopen(BASE + caminho) as r:
        return json.loads(r.read())


def post_json(caminho, corpo):
    req = urllib.request.Request(BASE + caminho, data=json.dumps(corpo).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def enviar(ws, arquivos):
    limite = "----concilia"
    partes = []
    for arq in arquivos:
        partes.append(f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivos\"; filename=\"{arq.name}\"\r\n"
                      f"Content-Type: application/octet-stream\r\n\r\n".encode() + arq.read_bytes() + b"\r\n")
    corpo = b"".join(partes) + f"--{limite}--\r\n".encode()
    req = urllib.request.Request(f"{BASE}/api/ws/{ws}/envios", data=corpo, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


for _ in range(30):
    try:
        get("/api/estado")
        break
    except Exception:
        time.sleep(1)

e = enviar("horizonte", [EX / "lote-misturado-horizonte.pdf", EX / "foto-aso-celular.jpg"])
print("envio", e["id"], e["status"], e["total"], "páginas")
falhou_uma_vez = False
t0 = time.time()
while True:
    d = get(f"/api/envios/{e['id']}")
    st, feitas = d["envio"]["status"], d["envio"]["feitas"]
    if feitas >= 5 and not falhou_uma_vez:
        post_json(f"/api/envios/{e['id']}/simular-falha", {})
        falhou_uma_vez = True
    if st == "concluido":
        break
    if time.time() - t0 > 600:
        print("tempo esgotado", st, feitas)
        break
    time.sleep(1)
print(f"concluído em {time.time() - t0:.0f}s")
for p in d["paginas"]:
    print(f"  pág {p['n']:>2} {'NOVO' if p['inicio'] else '    '} {p['tipo']:<26} {p['conf']:>3}%  {p['fonte_texto']}  | {'; '.join(p['sinais'])[:110]}")
print("documentos:")
for doc in d["docs"]:
    print(f"  #{doc['id']} {doc['tipo']:<26} págs {doc['pag_ini']}-{doc['pag_fim']} {doc['conf']}% {doc['status']:<10} {doc['pessoa']} | {doc['cpf']}")
print("eventos:")
for ev in d["eventos"]:
    print("  ", ev["texto"])
print("busca 'hemograma':", [(r["tipo"], r["trecho"][:60]) for r in get("/api/ws/horizonte/busca?q=hemograma")])
print("busca 'salario':", [(r["tipo"], r["pessoa"]) for r in get("/api/ws/horizonte/busca?q=salario")])
print("pendências:", [(p["tipo"], p["duvida"], p["conf"]) for p in get("/api/ws/horizonte/pendencias")["pendencias"]])
m = get("/api/ws/horizonte/matriz")
for g in m["grupos"]:
    for l in g["linhas"]:
        print("  matriz", g["empresa"], "|", l["pessoa"], [c["status"] for c in l["celulas"]])
doc1 = get(f"/api/docs/{d['docs'][0]['id']}")
print("texto mascarado:", doc1["texto"][:300].replace("\n", " / "))
