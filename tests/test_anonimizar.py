from PIL import Image

from app import anonimizar


def test_esconde_cpf_conta_e_saude():
    texto = "CPF: 321.654.987-00\nDepósito: Agência 1234, Conta 56789-0\nObservação: CID Z00.0"
    saida = anonimizar.mascarar_texto(texto, ["cpf", "banco", "saude"])
    assert "321.654.987-00" not in saida
    assert "56789-0" not in saida
    assert "Z00.0" not in saida
    assert "CPF/RG protegido" in saida


def test_categoria_desligada_continua_visivel():
    saida = anonimizar.mascarar_texto("CPF: 321.654.987-00", [])
    assert "321.654.987-00" in saida


def test_tarja_na_imagem(tmp_path):
    png = tmp_path / "p.png"
    Image.new("RGB", (400, 100), "white").save(png)
    linhas = [{"text": "CPF: 321.654.987-00", "box": [10, 10, 390, 40]}]
    im = anonimizar.mascarar_imagem(str(png), linhas, ["cpf"])
    assert im.getpixel((300, 25)) == (15, 30, 61)   # parte do CPF pintada
    assert im.getpixel((20, 80)) == (255, 255, 255)  # fora da linha intacto
