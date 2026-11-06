#!/usr/bin/env python3
"""Gera lote de testes inteiramente sintético e gabarito, de forma determinística.

Não utiliza serviços externos. PREMISSA: XML tem esquema DIDÁTICO, não é XML NFS-e oficial.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
import json
import random
from pathlib import Path
import re
import shutil
from xml.etree.ElementTree import Element, SubElement, ElementTree

from faker import Faker
from PIL import Image, ImageEnhance, ImageFilter
import fitz
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4
TYPES = ('contrato', 'nota_fiscal_servico', 'aditivo_contratual', 'medicao_ou_relatorio_servico', 'comprovante_pagamento')
SERVICES = ['Manutenção predial', 'Limpeza e conservação', 'Suporte técnico', 'Vigilância patrimonial', 'Jardinagem', 'Gestão de resíduos', 'Manutenção de equipamentos', 'Serviços de recepção']


def cnpj_valid(number: str) -> bool:
    digits = re.sub(r'\D', '', number)
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    for length in (12, 13):
        weights = ([5,4,3,2,9,8,7,6,5,4,3,2] if length == 12 else [6,5,4,3,2,9,8,7,6,5,4,3,2])
        rem = sum(int(d) * w for d, w in zip(digits[:length], weights)) % 11
        if int(digits[length]) != (0 if rem < 2 else 11-rem):
            return False
    return True


def synthetic_cnpj(index: int) -> str:
    # Sequência reservada PARA TESTES APENAS. DV válido não garante CNPJ não atribuído.
    base = f'{87000000 + index:08d}{(1000 + index) % 10000:04d}'
    for weights in ([5,4,3,2,9,8,7,6,5,4,3,2], [6,5,4,3,2,9,8,7,6,5,4,3,2]):
        rem = sum(int(n)*weight for n, weight in zip(base, weights)) % 11
        base += str(0 if rem < 2 else 11-rem)
    return f'{base[:2]}.{base[2:5]}.{base[5:8]}/{base[8:12]}-{base[12:]}'


def money(num: Decimal | int | float) -> str:
    return f'R$ {Decimal(str(num)):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')


def write_pdf(path: Path, title: str, lines: list[str], page_count: int, *, noisy: bool = False, footer: bool = True) -> None:
    """Cria PDF multi-página com cabeçalhos, texto e paginação, opcionalmente digitalizado."""
    path.parent.mkdir(parents=True, exist_ok=True)
    output = BytesIO() if noisy else str(path)
    pdf = canvas.Canvas(output, pagesize=A4, pageCompression=1)
    for page in range(1, page_count+1):
        pdf.setFillColor(colors.HexColor('#1e3550'))
        pdf.setFont('Helvetica-Bold', 14)
        pdf.drawString(48, 780, title[:77])
        pdf.setStrokeColor(colors.HexColor('#a0b1c5'))
        pdf.line(48, 767, PAGE_W-48, 767)
        pdf.setFillColor(colors.black)
        pdf.setFont('Helvetica', 10)
        pdf.drawString(48, 740, 'CONCILIA AI - MATERIAL SINTETICO DE DEMONSTRACAO')
        # Repete informação-chave em todas as páginas para permitir teste de continuidade.
        base_y = 715
        for i, line in enumerate(lines[:12]):
            pdf.drawString(48, base_y-i*22, str(line)[:96])
        if page_count > 1:
            pdf.setFont('Helvetica', 10)
            pdf.drawString(48, 385, f'Secao {page}: demonstracao de continuidade de documento e agrupamento de paginas.')
            pdf.drawString(48, 365, 'Texto adicional de apoio ao processamento documental, sem dados reais.')
        if footer:
            pdf.setFont('Helvetica', 9)
            pdf.drawRightString(PAGE_W-50, 35, f'Pagina {page} de {page_count}')
        pdf.showPage()
    pdf.save()
    if noisy:
        source = fitz.open(stream=output.getvalue(), filetype='pdf')
        scanned = fitz.open()
        rng = random.Random(int.from_bytes(path.name.encode()[:8], 'big'))
        for pg in source:
            pix = pg.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
            image = Image.frombytes('RGB', [pix.width, pix.height], pix.samples)
            if rng.random() < .7:
                image = image.rotate(rng.choice([-.7, .5, 1.0]), expand=False, fillcolor='white')
            if rng.random() < .4:
                image = ImageEnhance.Contrast(image).enhance(.85)
                image = image.filter(ImageFilter.GaussianBlur(radius=.22))
            buf = BytesIO()
            image.save(buf, format='JPEG', quality=82)
            new = scanned.new_page(width=PAGE_W, height=PAGE_H)
            new.insert_image(new.rect, stream=buf.getvalue())
        scanned.save(str(path), deflate=True)
        scanned.close()
        source.close()


def write_xml(path: Path, inv: dict) -> None:
    # PREMISSA: Estrutura XML DIDÁTICA; não equivale ao leiaute nacional oficial de NFS-e.
    root = Element('NfseDemonstracao', {'schema': 'concilia-ai-synthetic-v1'})
    for key in ('numero', 'data_emissao', 'competencia', 'prestador_cnpj', 'tomador_cnpj', 'descricao_servico', 'valor_servico'):
        SubElement(root, key).text = str(inv[key])
    ElementTree(root).write(path, encoding='utf-8', xml_declaration=True)


def generate(out: Path, supplier_count: int = 20, invoices_per_supplier: int = 3, seed: int = 2026, scan: bool = True) -> dict:
    """Gera PDFs individuais, XML didáticos e PDF misturado com mapa página-documento."""
    if supplier_count < 3 or invoices_per_supplier < 3:
        raise ValueError('Use pelo menos 3 fornecedores e 3 notas por fornecedor.')
    rng = random.Random(seed)
    fake = Faker('pt_BR')
    Faker.seed(seed)
    if out.exists():
        # Para prevenir destruição acidental, só permite regenerar diretório com marcador.
        if not (out / '.concilia_synthetic').exists():
            raise FileExistsError(f'Pasta {out} já existe e não foi criada pelo gerador; escolha outra.')
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / '.concilia_synthetic').write_text('Somente dados sintéticos gerados automaticamente.\n', encoding='utf-8')
    for section in ('contratos', 'notas_pdf', 'notas_xml', 'aditivos', 'lotes', 'outros'):
        (out / section).mkdir()

    suppliers = []
    documents = []
    invoices = []
    divergences = []
    contracts = []
    additions = []
    buyer_cnpj = synthetic_cnpj(999)
    base_date = date(2026, 8, 1)

    def register(doc_id: str, doc_type: str, path: Path, pages: int, supplier_id: str | None, expected_fields: dict, scan_pdf: bool = False):
        documents.append({'document_id':doc_id, 'type':doc_type, 'supplier_id':supplier_id,
                          'file':str(path.relative_to(out)), 'pages':pages, 'is_scanned':scan_pdf,
                          'expected_fields':expected_fields})

    for i in range(supplier_count):
        supplier_id = f'FOR-{i+1:03d}'
        cnpj = synthetic_cnpj(i+1)
        name = fake.unique.company()
        service = SERVICES[i % len(SERVICES)]
        value = Decimal(4000 + 350*i)
        supplier = {'supplier_id':supplier_id, 'cnpj':cnpj, 'razao_social':name, 'servico':service}
        suppliers.append(supplier)
        contract_id = f'CTR-{i+1:03d}'
        contract = {'contract_id':contract_id, 'supplier_id':supplier_id, 'prestador_cnpj':cnpj,
                    'tomador_cnpj':buyer_cnpj, 'valor_mensal':str(value), 'objeto':service,
                    'vigencia_inicio':'2026-01-01','vigencia_fim':'2026-12-31'}
        contracts.append(contract)
        lines = [f'Instrumento: {contract_id}', f'Contratada: {name}', f'CNPJ contratada: {cnpj}',
                 f'CNPJ contratante: {buyer_cnpj}', f'Objeto: {service}', f'Valor mensal: {money(value)}',
                 'Vigencia: 01/01/2026 a 31/12/2026', 'Pagamento mensal conforme medicao de servicos.',
                 'Reajustes dependem de termo aditivo formal e valido.']
        path = out/'contratos'/f'{contract_id}.pdf'
        # 9 páginas x 20 contratos = 180 páginas
        write_pdf(path, 'CONTRATO DE PRESTACAO DE SERVICOS', lines, 9, noisy=scan and i % 3 == 0)
        register(contract_id, 'contrato', path, 9, supplier_id, contract, scan and i%3 == 0)

        # Um aditivo válido em fornecedor 0 e um fora da vigência em fornecedor 1.
        if i in (0,1):
            amendment_id = f'ADT-{i+1:03d}'
            valid = i == 0
            a = {'amendment_id': amendment_id, 'contract_id':contract_id,
                 'valor_adicional':'2500.00', 'vigencia_inicio':'2026-08-01' if valid else '2026-02-01',
                 'vigencia_fim':'2026-12-31' if valid else '2026-03-31'}
            additions.append(a)
            apath = out/'aditivos'/f'{amendment_id}.pdf'
            write_pdf(apath, 'TERMO ADITIVO CONTRATUAL', [f'Aditivo: {amendment_id}', f'Contrato: {contract_id}',
                f'Fornecedor: {cnpj}', f'Acrescimo mensal: {money(2500)}',
                f'Vigencia do aditivo: {a["vigencia_inicio"]} ate {a["vigencia_fim"]}'], 2)
            register(amendment_id, 'aditivo_contratual', apath, 2, supplier_id, a)

        for j in range(invoices_per_supplier):
            invoice_id = f'NF-{i+1:03d}-{j+1:02d}'
            issue = base_date + timedelta(days=30*j)
            amount = value
            descr = service
            target_contract = contract_id
            reasons = []
            if i == 0 and j == 0:
                amount += Decimal(2500)
                reasons.append('VALOR_JUSTIFICADO_ADITIVO')
            elif i == 1 and j == 0:
                amount += Decimal(2500)
                reasons.extend(['R02_VALOR_DIVERGENTE', 'ADITIVO_FORA_VIGENCIA'])
            elif i == 2 and j == 0:
                amount += Decimal(2500)
                reasons.append('R02_VALOR_DIVERGENTE')
            elif i == 3 and j == 0:
                descr = 'Consultoria financeira nao contratada'
                reasons.append('R04_SERVICO_DIVERGENTE')
            elif i == 4 and j == 0:
                issue = date(2027, 2, 12)
                reasons.append('R05_FORA_VIGENCIA')
            elif i == 5 and j == 1:
                reasons.append('R07_DUPLICADA')
            elif i == 6 and j == 0:
                target_contract = None
                reasons.append('SEM_CONTRATO')
            invoice = {'invoice_id':invoice_id, 'numero':f'{30000 + i*100+j}',
                       'data_emissao':issue.isoformat(), 'competencia':issue.strftime('%Y-%m'),
                       'prestador_cnpj':synthetic_cnpj(700+i) if i == 6 and j == 0 else cnpj, 'tomador_cnpj':buyer_cnpj,
                       'descricao_servico':descr, 'valor_servico':str(amount),
                       'contract_id':target_contract, 'scenario_reasons':reasons}
            if i == 5 and j == 1:
                invoice['numero'] = invoices[-1]['numero']  # nota anterior do mesmo fornecedor
            invoices.append(invoice)
            if reasons:
                divergences.append({'invoice_id':invoice_id,'reasons':reasons,
                                    'expected_value':str(value),'observed_value':str(amount),
                                    'evidence_document_id':invoice_id})
            ppath = out/'notas_pdf'/f'{invoice_id}.pdf'
            lines = [f'Numero: {invoice["numero"]}', f'Prestador: {name}', f'CNPJ prestador: {invoice["prestador_cnpj"]}',
                     f'CNPJ tomador: {buyer_cnpj}', f'Data emissao: {invoice["data_emissao"]}',
                     f'Competencia: {invoice["competencia"]}', f'Descricao: {descr}',
                     f'Valor do servico: {money(amount)}', f'Contrato referenciado: {target_contract or "nao informado"}']
            write_pdf(ppath, 'NOTA FISCAL DE SERVICOS - DEMONSTRACAO', lines, 2, noisy=scan and j == 2)
            register(invoice_id, 'nota_fiscal_servico', ppath, 2, supplier_id, invoice, scan and j == 2)
            xpath = out/'notas_xml'/f'{invoice_id}.xml'
            write_xml(xpath, invoice)

    # 20x9 + 60x2 + 2x2 = 304 páginas. Embaralha DOCUMENTOS (não páginas).
    rng.shuffle(documents)
    combined = fitz.open()
    page_map = []
    boundary_pages = []
    for doc in documents:
        source = fitz.open(out/doc['file'])
        start = len(combined)+1
        combined.insert_pdf(source)
        end = len(combined)
        source.close()
        boundary_pages.append(start)
        doc['batch_start_page'] = start
        doc['batch_end_page'] = end
        for internal_page in range(1, doc['pages']+1):
            page_map.append({'batch_page':start+internal_page-1, 'document_id':doc['document_id'],
                             'document_page':internal_page, 'type':doc['type']})
    combined_file = out/'lotes'/'lote_misturado.pdf'
    combined.save(str(combined_file), deflate=True, garbage=3)
    combined.close()
    truth = {'schema_version':'1.0', 'seed':seed, 'generated_date': '2026-11-06',
             'premissas': ['CNPJ sintético com dígito verificador válido, sem consulta à Receita: não assegura ausência de atribuição real.',
                'XML demonstrativo NÃO segue necessariamente o padrão nacional de NFS-e.',
                'Documentos contêm dados e cenários artificiais; divergências são gabarito, não constatação fiscal.'],
             'batch_file':str(combined_file.relative_to(out)), 'batch_total_pages':len(page_map),
             'document_count':len(documents), 'supplier_count':supplier_count,
             'boundary_start_pages':boundary_pages, 'page_map':page_map,
             'suppliers':suppliers, 'contracts':contracts, 'amendments':additions,
             'invoices':invoices, 'documents':documents, 'expected_findings':divergences}
    (out/'ground_truth.json').write_text(json.dumps(truth,ensure_ascii=False, indent=2), encoding='utf-8')
    report = {'total_pages':len(page_map), 'pdf_documents':len(documents), 'invoice_xml_files':len(invoices),
              'types':dict(Counter(d['type'] for d in documents)), 'findings':len(divergences),
              'scan_count':sum(d['is_scanned'] for d in documents), 'first_pages':boundary_pages[:5]}
    (out/'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main():
    ap = argparse.ArgumentParser(description='Gera documentos sintéticos e ground_truth para Concilia AI.')
    ap.add_argument('--output', type=Path, default=Path('data/synthetic'))
    ap.add_argument('--suppliers', type=int, default=20)
    ap.add_argument('--invoices-per-supplier', type=int, default=3)
    ap.add_argument('--seed', type=int, default=2026)
    ap.add_argument('--no-scan', action='store_true', help='Desativa simulação de documentos digitalizados (mais rápido).')
    args = ap.parse_args()
    print(json.dumps(generate(args.output, args.suppliers, args.invoices_per_supplier, args.seed, not args.no_scan), indent=2))


if __name__ == '__main__':
    main()
