"""Mede o custo REAL da IA (Claude) por página, com chamadas de verdade à API.

Usa o mesmo pedido que o sistema faz em produção (app/analise.py: imagem + texto do OCR) e soma os tokens
que a própria API informa em cada resposta (usage). O custo sai desses tokens x preço oficial por token.

Precisa de ANTHROPIC_API_KEY no .env. Cada página é uma chamada paga (centavos).

Uso:
  .venv\\Scripts\\python.exe ferramentas\\medir_custo_ia.py [arquivo] [--paginas 10] [--modelos opus,sonnet,haiku] [--dolar 5.40]

Padrão: as 10 primeiras páginas do lote digitalizado de casos-de-teste, só no modelo do sistema (Opus 5.5).
"""
import argparse
import json
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CONCILIA_DADOS", tempfile.mkdtemp(prefix="concilia-custo-"))

from app import analise, config, ocr, seed  # noqa: E402

# Preço oficial por milhão de tokens (US$), Claude API, tabela da Anthropic (out/2026).
# Haiku 5.5: vale para pedidos de até 100 mil tokens (cada página fica bem abaixo disso).
PRECOS = {
    "opus": ("claude-opus-5-5", 4.00, 20.00),
    "sonnet": ("claude-sonnet-5-5", 2.00, 10.00),
    "haiku": ("claude-haiku-5-5", 0.10, 0.50),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("arquivo", nargs="?", default=None)
    ap.add_argument("--paginas", type=int, default=10)
    ap.add_argument("--modelos", default="opus")
    ap.add_argument("--dolar", type=float, default=None, help="câmbio para mostrar em reais (ex.: 5.40)")
    a = ap.parse_args()

    if not config.claude_configurado():
        sys.exit("Sem ANTHROPIC_API_KEY. Coloque a chave no arquivo .env e rode de novo.")
    arquivo = a.arquivo or next(iter(sorted((config.BASE / "casos-de-teste").glob("01-*.tif"))), None)
    if not arquivo:
        sys.exit("Informe um arquivo ou gere os casos: .venv\\Scripts\\python.exe ferramentas\\gerar_casos_teste.py")
    tipos = [{"nome": n, "titulos": t, "palavras": p} for n, (t, p) in seed.TIPOS.items()]

    # 1) OCR local das páginas (grátis), uma vez só.
    paginas = ocr.contar_paginas(str(arquivo))[: a.paginas]
    lidas = []
    for i, (idx, origem) in enumerate(paginas):
        png = str(Path(os.environ["CONCILIA_DADOS"]) / f"p{i:03d}.png")
        _, _, texto, _, _ = ocr.renderizar(str(arquivo), idx, origem, png)
        lidas.append((png, texto))
    print(f"{len(lidas)} página(s) de {Path(arquivo).name} lidas pelo OCR local.\n")

    resultado = {}
    for chave in [m.strip() for m in a.modelos.split(",") if m.strip()]:
        modelo, p_in, p_out = PRECOS[chave]
        config.MODELO = modelo
        analise.USOS.clear()
        anterior, tempos, erros = None, [], 0
        for png, texto in lidas:
            t = time.time()
            try:
                r = analise.analisar_claude(png, texto, tipos, anterior)
                anterior = {"tipo": r["tipo"], "pessoa": r["pessoa"], "cpf": r["cpf"]}
            except Exception as e:  # recusa, limite, rede: registra e segue
                erros += 1
                print(f"  {modelo}: erro numa página ({e})")
            tempos.append(time.time() - t)
        usos = [u for u in analise.USOS if u["etapa"] == "pagina"]
        if not usos:
            print(f"{modelo}: nenhuma resposta medida.\n")
            continue
        ent = [u["entrada"] + u["cache_escrita"] + u["cache_leitura"] for u in usos]
        sai = [u["saida"] for u in usos]
        custos = [(u["entrada"] * p_in + u["saida"] * p_out) / 1e6 for u in usos]
        por_pag = statistics.mean(custos)
        resultado[modelo] = {"paginas": len(usos), "erros": erros, "entrada_media": statistics.mean(ent),
                             "saida_media": statistics.mean(sai), "usd_por_pagina": por_pag,
                             "segundos_por_pagina": statistics.mean(tempos), "modelos_que_responderam": sorted({u["modelo"] for u in usos})}
        brl = f" | R$ {por_pag * a.dolar:.4f}" if a.dolar else ""
        print(f"{modelo}: {len(usos)} página(s) medidas, {erros} erro(s)")
        print(f"  tokens por página: entrada {statistics.mean(ent):.0f} (mín {min(ent)}, máx {max(ent)}), "
              f"saída {statistics.mean(sai):.0f} (mín {min(sai)}, máx {max(sai)})")
        print(f"  custo por página: US$ {por_pag:.5f}{brl}   tempo médio: {statistics.mean(tempos):.1f}s")
        for volume in (1_000, 10_000, 100_000):
            total = por_pag * volume
            print(f"  {volume:>7,} páginas: US$ {total:,.2f}" + (f" | R$ {total * a.dolar:,.2f}" if a.dolar else "")
                  + f"   (só as ~15% duvidosas: US$ {total * 0.15:,.2f})")
        print()
    saida = config.BASE / "casos-de-teste" / "custo-ia-medido.json"
    saida.parent.mkdir(exist_ok=True)
    saida.write_text(json.dumps({"arquivo": str(arquivo), "precos_usd_por_milhao": PRECOS, "dolar": a.dolar,
                                 "resultado": resultado}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Resultado salvo em {saida}")


if __name__ == "__main__":
    main()
