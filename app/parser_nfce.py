"""Parser específico NFC-e modelo 65.

Aproveita a base estrutural compartilhada com NF-e, mas trata o modelo 65
separadamente (consumidor, totais e pagamentos).
"""
from .parser_nfe import _ler_nfe
from .fiscal_xml_comum import abrir, unico, filho, filhos, texto, decimal


def ler_nfce(conteudo: bytes):
    obj = _ler_nfe(conteudo, "65")
    raiz = abrir(conteudo)
    inf = unico(raiz, "infNFe")
    ide = filho(inf, "ide")
    destinatario = filho(inf, "dest")
    obj["campos"]["consumidor_identificado"] = bool(
        texto(destinatario, "CPF") or texto(destinatario, "CNPJ"))
    obj["campos"]["presenca_comprador"] = texto(ide, "indPres")
    obj["campos"]["qr_code"] = texto(filho(inf, "infNFeSupl"), "qrCode")
    # infNFeSupl é irmão de infNFe, não seu filho.
    if not obj["campos"]["qr_code"]:
        nfe = next((e for e in raiz.iter() if e is not inf and
                    any(c is inf for c in e)), None)
        obj["campos"]["qr_code"] = texto(nfe, "infNFeSupl/qrCode")
    obj["campos"]["troco"] = decimal(filho(inf, "pag"), "vTroco")
    obj["campos"]["valor_total"] = obj["campos"]["totais"]["nota"]
    return obj
