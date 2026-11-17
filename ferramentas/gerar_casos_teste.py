"""Gera a pasta casos-de-teste/ com arquivos fictícios para a demonstração.

Todos os documentos são dos MESMOS fornecedores (mesma semente do gerador), para mostrar que a Concilia
relaciona notas, contratos e problemas entre envios diferentes.

Uso:
  Linux:   .venv/bin/python ferramentas/gerar_casos_teste.py [fornecedores]
  Windows: .venv\Scripts\python.exe ferramentas\gerar_casos_teste.py [fornecedores]
  (padrão: 20 -> ~300 páginas)
"""
import io
import json
import random
import shutil
import sys
import zipfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymupdf as fitz  # noqa: E402
from PIL import Image, ImageEnhance, ImageFilter  # noqa: E402

from app import avaliacao, fiscal  # noqa: E402
from app.config import BASE  # noqa: E402

SAIDA = BASE / "casos-de-teste"
TOMADOR = "Atlântica Facilities S.A."


def escanear(paginas: list, destino: Path, semente: int, cortar: dict | None = None):
    """Grava as páginas (de PDFs) como um PDF só de imagem, como sai de um scanner.
    cortar = {índice: fração}: a folha sai cortada a partir dessa altura (scanner puxou torto)."""
    rng = random.Random(semente)
    out = fitz.open()
    for i, pg in enumerate(paginas):
        pix = pg.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), colorspace=fitz.csGRAY)
        im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
        im = im.rotate(rng.choice([-0.8, 0.5, 1.0]), fillcolor=255).filter(ImageFilter.GaussianBlur(0.4))
        if cortar and i in cortar:
            corte = int(im.height * cortar[i])
            im.paste(255, (0, corte, im.width, im.height))
            im = ImageEnhance.Contrast(im).enhance(0.9)
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=80)
        nova = out.new_page(width=pg.rect.width, height=pg.rect.height)
        nova.insert_image(nova.rect, stream=buf.getvalue())
    out.save(destino, deflate=True)


def paginas_de(pdf: Path) -> tuple:
    d = fitz.open(pdf)
    return d, [d[i] for i in range(d.page_count)]


def main():
    fornecedores = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    fornecedores = max(10, fornecedores)
    print(f"Gerando lote fictício com {fornecedores} fornecedores…")
    pasta = avaliacao.gerar_lote(fornecedores=fornecedores, notas=3, digitalizar=True, semente=2026)
    gab = json.loads((pasta / "ground_truth.json").read_text(encoding="utf-8"))
    nomes = {s["cnpj"]: s["razao_social"] for s in gab["suppliers"]}
    notas = {inv["invoice_id"]: inv for inv in gab["invoices"]}
    if SAIDA.exists():
        shutil.rmtree(SAIDA)
    SAIDA.mkdir()

    # 01: lote grande, só imagem.
    total = gab["batch_total_pages"]
    tif = avaliacao.digitalizar(pasta / "lotes" / "lote_misturado.pdf", SAIDA / f"01-lote-grande-{total}-paginas.tif", semente=2026)
    print(f"  01 lote grande: {total} páginas, {tif.stat().st_size / 1e6:.0f} MB")

    # 02: XML de todas as notas do lote (como viriam do Emissor Nacional).
    with zipfile.ZipFile(SAIDA / "02-notas-do-lote-xml.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for inv in gab["invoices"]:
            nome = nomes.get(inv["prestador_cnpj"], "Prestador sem contrato ME")
            z.writestr(f"NFSe-{inv['numero']}-{inv['invoice_id']}.xml", fiscal.nfse_nacional_xml(inv, nome, TOMADOR))

    # 03: contrato com a página 4 escaneada duas vezes.
    d, pgs = paginas_de(pasta / "contratos" / "CTR-008.pdf")
    escanear(pgs[:4] + [pgs[3]] + pgs[4:], SAIDA / "03-contrato-CTR-008-pagina-repetida.pdf", 3)
    d.close()

    # 04: contrato sem a página 6.
    d, pgs = paginas_de(pasta / "contratos" / "CTR-009.pdf")
    escanear(pgs[:5] + pgs[6:], SAIDA / "04-contrato-CTR-009-falta-pagina-6.pdf", 4)
    d.close()

    # 05: nota em PDF com a folha cortada (o valor ficou de fora).
    d, pgs = paginas_de(pasta / "notas_pdf" / "NF-004-02.pdf")
    escanear(pgs, SAIDA / "05-nota-30301-folha-cortada.pdf", 5, cortar={0: 0.29, 1: 0.29})
    d.close()

    # 06: a mesma nota do lote enviada de novo.
    inv = notas["NF-001-02"]
    (SAIDA / f"06-nota-{inv['numero']}-reenviada.xml").write_bytes(fiscal.nfse_nacional_xml(inv, nomes[inv["prestador_cnpj"]], TOMADOR))

    # 07: outra nota do mesmo prestador com o MESMO número (cobrança em dobro).
    base = notas["NF-010-03"]
    dup = dict(base, data_emissao="2026-10-20", competencia="2026-10", invoice_id="NF-010-99")
    (SAIDA / f"07-nota-{dup['numero']}-mesmo-numero.xml").write_bytes(fiscal.nfse_nacional_xml(dup, nomes[dup["prestador_cnpj"]], TOMADOR))

    # 08: nota nova cobrando R$ 1.000 acima do contrato.
    base = notas["NF-012-03"]
    acima = dict(base, numero=str(int(base["numero"]) + 50), data_emissao="2026-10-30", competencia="2026-10",
                 valor_servico=f"{float(base['valor_servico']) + 1000:.2f}", invoice_id="NF-012-98")
    (SAIDA / f"08-nota-{acima['numero']}-valor-acima.xml").write_bytes(fiscal.nfse_nacional_xml(acima, nomes[acima["prestador_cnpj"]], TOMADOR))

    # 09: nota de um prestador que não tem contrato com o cliente.
    sem = dict(base, numero="777", data_emissao="2026-10-10",
               competencia="2026-10", descricao_servico="Pintura de fachada", valor_servico="3200.00", invoice_id="NF-950-01")
    sem["prestador_cnpj"] = _cnpj_valido(950)
    (SAIDA / "09-nota-777-sem-contrato.xml").write_bytes(fiscal.nfse_nacional_xml(sem, "Pinturas Rápidas ME", TOMADOR))

    c = {s["cnpj"]: s for s in gab["suppliers"]}
    (SAIDA / "LEIA-ME.txt").write_text(f"""CASOS DE TESTE DA CONCILIA AI (dados fictícios, gerados em {date.today():%d/%m/%Y})

Use o cliente Atlântica Facilities (ou crie um novo). Envie na ordem, um de cada vez, em "Enviar documentos".

01-lote-grande-{total}-paginas.tif   ({fornecedores} fornecedores, contratos de 9 páginas, aditivos e notas misturados,
    TIFF só de imagem, ~6% das folhas tortas e borradas)
    Mostra: separação, agrupamento, classificação, OCR, confiança e fila de revisão em grande volume.
    Retomada: clique em "Simular queda" durante o processamento.
    Leva uns 2 a 3 segundos por página no notebook.

02-notas-do-lote-xml.zip   (o XML de cada nota do lote, no leiaute nacional v1.01)
    Mostra: XML lido sem OCR; cada nota conferida contra o contrato lido no 01.
    Esperado em Divergências: valor acima (aditivo vencido), valor acima, serviço diferente,
    fora da vigência, nota duplicada e fornecedor sem contrato.

03-contrato-CTR-008-pagina-repetida.pdf   (página 4 escaneada duas vezes)
    Esperado: vai para Dúvidas da leitura com "Página repetida: a página 4 de 9 aparece 2 vezes".

04-contrato-CTR-009-falta-pagina-6.pdf   (8 páginas de um contrato de 9)
    Esperado: vai para Dúvidas da leitura com "Documento incompleto: falta a página 6 de 9".

05-nota-30301-folha-cortada.pdf   (as duas folhas sairam cortadas no scanner)
    Esperado: classificada como nota fiscal, mas em Documentos aparece o aviso de que o valor não ficou legível
    e a nota não entra na conferência pelo PDF (o XML dela já está no 02).

06-nota-{notas['NF-001-02']['numero']}-reenviada.xml   (a mesma nota que já veio no 02)
    Esperado: não duplica; o envio diz que a nota já estava cadastrada.

07-nota-{notas['NF-010-03']['numero']}-mesmo-numero.xml   (outra nota de {c[notas['NF-010-03']['prestador_cnpj']]['razao_social']} com o mesmo número)
    Esperado: divergência "Nota possivelmente duplicada".

08-nota-{acima['numero']}-valor-acima.xml   ({c[base['prestador_cnpj']]['razao_social']} cobrando R$ 1.000,00 acima do contrato)
    Esperado: divergência "Valor acima do contratado", diferença de R$ 1.000,00.

09-nota-777-sem-contrato.xml   (Pinturas Rápidas ME, sem contrato com o cliente)
    Esperado: divergência crítica "Fornecedor sem contrato".

Extra: envie o 01 de novo. Esperado: arquivo ignorado por ser repetido (mesmo conteúdo).
""", encoding="utf-8")
    print(f"Pronto: {SAIDA}")


def _cnpj_valido(i: int) -> str:
    return avaliacao._gerador().synthetic_cnpj(i)


if __name__ == "__main__":
    main()
