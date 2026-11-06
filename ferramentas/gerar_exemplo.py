"""Gera um lote misturado de documentos FICTÍCIOS para testar a Concilia AI.

Saída na pasta exemplos/:
- lote-misturado-horizonte.pdf  (13 páginas: documentos de várias pessoas em sequência,
  algumas páginas como imagem digitalizada torta, para exercitar o OCR)
- foto-aso-celular.jpg           (um ASO fotografado com celular)
- lote-construtora.pdf           (para o cliente Construtora Vale Alto)
"""
import io
import random
from pathlib import Path

import pymupdf as fitz
from PIL import Image, ImageFilter

PASTA = Path(__file__).resolve().parent.parent / "exemplos"
PASTA.mkdir(exist_ok=True)
random.seed(7)
EMP = "Empresa: Serviços Litoral ME   CNPJ 12.345.678/0001-90"


def pagina(doc, linhas, titulo=None):
    pg = doc.new_page(width=595, height=842)
    y = 70
    if titulo:
        pg.insert_text((60, y), titulo, fontsize=17, fontname="hebo")
        y += 34
    for ln in linhas:
        if ln == "":
            y += 12
            continue
        pg.insert_text((60, y), ln, fontsize=11, fontname="helv")
        y += 19
    return pg


def como_imagem(doc_tmp, rot=1.2, ruido=True, desfoque=0.0):
    """Converte a última página em imagem 'digitalizada' (torta, cinza, com ruído)."""
    pg = doc_tmp[-1]
    pix = pg.get_pixmap(matrix=fitz.Matrix(2, 2))
    im = Image.open(io.BytesIO(pix.tobytes("png"))).convert("L")
    im = im.rotate(rot, expand=True, fillcolor=245)
    if ruido:
        px = im.load()
        for _ in range(im.width * im.height // 60):
            x, y = random.randrange(im.width), random.randrange(im.height)
            px[x, y] = random.choice((180, 210, 90))
    if desfoque:
        im = im.filter(ImageFilter.GaussianBlur(desfoque))
    return im


def lote_horizonte():
    final = fitz.open()
    def add_texto(linhas, titulo=None):
        pagina(final, linhas, titulo)
    def add_imagem(linhas, titulo=None, **kw):
        tmp = fitz.open()
        pagina(tmp, linhas, titulo)
        im = como_imagem(tmp, **kw)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        pg = final.new_page(width=im.width / 2, height=im.height / 2)
        pg.insert_image(pg.rect, stream=buf.getvalue())

    # 1-2 Ficha de registro (Marcos) com numeração
    add_texto([EMP, "", "Nome do colaborador: Marcos Antonio Silva", "CPF: 321.654.987-00",
               "Data de admissão: 01/10/2026", "Cargo: Porteiro", "Jornada: 12x36",
               "CTPS: 1234567 série 0012", "Salário contratual: R$ 1.850,00",
               "Endereço: Rua das Palmeiras, 145 - Recife/PE", "Telefone: (81) 99876-5432",
               "", "Página 1 de 2"], "FICHA DE REGISTRO DE EMPREGADO")
    add_texto(["Dependentes: não possui", "Vale-transporte: sim", "Banco para salário: Agência 1234, Conta 56789-0",
               "", "Declaro que as informações acima são verdadeiras.", "", "Assinatura do empregado: ________________",
               "Assinatura do empregador: ________________", "", "Página 2 de 2"])
    # 3 ASO (Marcos)
    add_texto([EMP, "", "Nome do colaborador: Marcos Antonio Silva", "CPF: 321.654.987-00",
               "Tipo de exame: Exame admissional", "Data do exame: 14/10/2026",
               "Riscos ocupacionais: ausência de riscos específicos", "Observação: CID Z00.0 - exame de rotina",
               "", "Resultado: APTO para a função", "", "Médico do trabalho: Dr. Paulo Mendes - CRM 12345/PE",
               "Coordenador do PCMSO"], "ATESTADO DE SAÚDE OCUPACIONAL - ASO")
    # 4 Exame complementar (Marcos) - digitalizado
    add_imagem(["Laboratório Vida Diagnósticos", "", "Paciente: Marcos Antonio Silva", "CPF: 321.654.987-00",
                "Material: sangue", "Exame: Hemograma completo", "Hemácias: 4,9 milhões/mm3",
                "Leucócitos: 6.800/mm3", "Valores de referência conforme idade e sexo", "", "Liberado em 13/10/2026"],
               "RESULTADO DE EXAME", rot=0.8)
    # 4b Segunda folha do exame, sem título nem numeração (fronteira duvidosa -> revisão humana)
    add_imagem(["Paciente: Marcos Antonio Silva", "", "Audiometria tonal: limiares dentro da normalidade",
                "Orelha direita: 20 dB", "Orelha esquerda: 20 dB", "", "Assinatura: Fga. Renata Lopes"],
               None, rot=-0.6)
    # 5 Holerite Marcos
    add_texto([EMP, "", "Nome do colaborador: Marcos Antonio Silva", "CPF: 321.654.987-00",
               "Competência: 10/2026", "", "Vencimentos", "  Salário base ............ R$ 1.850,00",
               "  Adicional noturno ....... R$ 214,60", "Descontos", "  INSS .................... R$ 158,20",
               "", "Líquido a receber: R$ 1.906,40", "Depósito: Agência 1234, Conta 56789-0"],
              "RECIBO DE PAGAMENTO DE SALÁRIO")
    # 6 Holerite Ana - digitalizado e torto (mesmo tipo, outra pessoa)
    add_imagem([EMP, "", "Nome do colaborador: Ana Beatriz Rocha", "CPF: 456.789.123-11",
                "Competência: 10/2026", "", "Vencimentos", "  Salário base ............ R$ 1.850,00",
                "Descontos", "  INSS .................... R$ 141,80", "", "Líquido a receber: R$ 1.708,20"],
               "RECIBO DE PAGAMENTO DE SALÁRIO", rot=-1.6)
    # 7 Guia FGTS (empresa)
    add_texto([EMP, "", "Competência: 10/2026", "Vencimento: 20/11/2026", "Trabalhadores na guia: 4",
               "Valor total do recolhimento: R$ 3.212,18", "", "Código de barras: 85800000032 12180385",
               "Recolhimento referente aos trabalhadores vinculados ao contrato"], "GUIA DO FGTS DIGITAL")
    # 8 Documento de identidade (Ana) - imagem
    add_imagem(["REPÚBLICA FEDERATIVA DO BRASIL", "Nome: Ana Beatriz Rocha", "Registro geral: 12.345.678-9",
                "Data de nascimento: 22/04/1994", "Naturalidade: Recife/PE", "Filiação: Maria Rocha e José Rocha",
                "Órgão expedidor: SDS/PE", "CPF: 456.789.123-11"], "CARTEIRA DE IDENTIDADE", rot=1.0)
    # 9-10 Cartão de ponto (Pedro) com numeração
    add_texto([EMP, "", "Nome do colaborador: Pedro Henrique Nunes", "CPF: 789.123.456-22",
               "Período: 01/10/2026 a 15/10/2026", "", "Dia   Entrada  Saída intervalo  Volta  Saída",
               "01/10  07:00    12:00            13:00  19:00", "02/10  07:02    12:00            13:00  19:05",
               "03/10  07:00    12:01            13:00  19:00", "", "Folha 1 de 2"], "CARTÃO DE PONTO")
    add_texto(["Dia   Entrada  Saída intervalo  Volta  Saída", "08/10  07:00    12:00            13:00  19:00",
               "09/10  06:58    12:00            13:00  21:00", "", "Horas extras no período: 4h",
               "", "Folha 2 de 2"])
    # 11 Comprovante fotografado, borrado (vai para revisão)
    add_imagem(["Banco Exemplo", "Favorecido: Pedro H. Nunes", "Valor: R$ 2.410,00", "Data: 03/11/2026",
                "Autenticação: 9F3A-77B1"], None, rot=3.5, desfoque=1.6)
    # 12 CND Federal
    add_texto(["Ministério da Fazenda - Receita Federal do Brasil", "", "Nome: Serviços Litoral ME",
               "CNPJ: 12.345.678/0001-90", "Não constam pendências em nome do sujeito passivo.",
               "Emitida em 02/09/2026", "Válida até 01/03/2027", "Dívida Ativa da União: nada consta"],
              "CERTIDÃO NEGATIVA DE DÉBITOS RELATIVOS AOS TRIBUTOS FEDERAIS")
    final.save(PASTA / "lote-misturado-horizonte.pdf")

    # Foto de ASO pelo celular (Pedro)
    tmp = fitz.open()
    pagina(tmp, [EMP, "", "Nome do colaborador: Pedro Henrique Nunes", "CPF: 789.123.456-22",
                 "Tipo de exame: Exame periódico", "Data do exame: 22/10/2026", "Resultado: APTO", "",
                 "Médico do trabalho: Dra. Lúcia Prado - CRM 54321/PE"], "ATESTADO DE SAÚDE OCUPACIONAL - ASO")
    im = como_imagem(tmp, rot=-2.5).convert("RGB")
    im.save(PASTA / "foto-aso-celular.jpg", quality=80)


def lote_construtora():
    d = fitz.open()
    emp = "Empresa: Fortes Estruturas ME   CNPJ 98.765.432/0001-10"
    pagina(d, [emp, "", "Nome do colaborador: Cícero Alves Lima", "CPF: 147.258.369-33", "Curso: Trabalho em altura",
               "Carga horária: 8 horas", "Concluído em 12/03/2026", "Validade: 2 anos", "", "Instrutor: Eng. Rafael Costa"],
           "CERTIFICADO DE TREINAMENTO NR-35")
    pagina(d, [emp, "", "Nome do colaborador: Cícero Alves Lima", "CPF: 147.258.369-33", "Função: Armador",
               "Riscos: queda de altura, ruído", "EPI obrigatório: capacete, cinto paraquedista, luvas",
               "", "Ciente: ______________________"], "ORDEM DE SERVIÇO DE SEGURANÇA DO TRABALHO")
    pagina(d, [emp, "", "Nome do colaborador: Cícero Alves Lima", "CPF: 147.258.369-33",
               "Tipo de exame: Exame admissional", "Resultado: APTO para trabalho em altura",
               "Médico do trabalho: Dr. Paulo Mendes"], "ATESTADO DE SAÚDE OCUPACIONAL - ASO")
    d.save(PASTA / "lote-construtora.pdf")


if __name__ == "__main__":
    lote_horizonte()
    lote_construtora()
    print("Exemplos gerados em", PASTA)
