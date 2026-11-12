"""Gera um lote sintético com gabarito, processa e mostra o acerto da IA (servidor precisa estar aberto).

Uso:  .venv\\Scripts\\python.exe ferramentas\\medir_acerto.py [fornecedores]
"""
import http.cookiejar
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
abrir = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def chamar(caminho, corpo=None):
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(BASE + caminho, data=dados, method="POST" if dados else "GET",
                                 headers={"Content-Type": "application/json"})
    with abrir.open(req) as r:
        return json.loads(r.read())


for _ in range(30):
    try:
        chamar("/api/estado")
        break
    except Exception:
        time.sleep(1)
chamar("/api/login", {"usuario": "admin", "senha": "admin123"})
fornecedores = int(sys.argv[1]) if len(sys.argv) > 1 else 8
e = chamar("/api/ws/atlantica/avaliacao", {"fornecedores": fornecedores})
print(f"Envio #{e['id']}: {e['total']} páginas")
t0 = time.time()
while True:
    estado = chamar(f"/api/envios/{e['id']}")["envio"]
    if estado["status"] == "concluido":
        break
    time.sleep(2)
print(f"Processado em {time.time() - t0:.0f}s")
r = next(x["resultado"] for x in chamar("/api/ws/atlantica/avaliacoes") if x["envio"]["id"] == e["id"])
for k in ("documentos_gabarito", "documentos_previstos", "fronteira_precisao", "fronteira_cobertura", "fronteira_f1",
          "segmentacao_exata", "tipo_correto", "paginas_tipo_correto", "pct_revisao", "acerto_automaticos"):
    print(f"  {k}: {r[k]}")
for erro in r["erros"]:
    print("  erro:", erro)
k = r["conciliacao"]
print("Conferência das notas:")
for chave in ("notas_gabarito", "notas_lidas", "divergencias_esperadas", "detectadas", "falsos_alarmes",
              "cobertura", "precisao", "regra_certa"):
    print(f"  {chave}: {k[chave]}")
for erro in k["erros"]:
    print("  erro:", erro)
