"""Roteador fiscal: NFS-e continua com parser legado; modelos 55,65,57 têm parsers específicos."""
from .fiscal_xml_comum import XMLFiscalErro, abrir, unico, filho, texto, local
from .parser_nfe import ler_nfe
from .parser_nfce import ler_nfce
from .parser_cte import ler_cte
from .validador_xsd import validar_xsd


def detectar_modelo(conteudo: bytes):
    raiz = abrir(conteudo)
    # CT-e pode conter <infNFe> como REFERÊNCIA em infDoc/infNFe.
    # Só reconhecemos documentos principais quando infNFe é filho direto
    # de <NFe> e infCte é filho direto de <CTe>.
    nfes = [e for pai in raiz.iter() if local(pai.tag) == "NFe"
            for e in pai if local(e.tag) == "infNFe"]
    ctes = [e for pai in raiz.iter() if local(pai.tag) == "CTe"
            for e in pai if local(e.tag) == "infCte"]
    if nfes and ctes:
        raise XMLFiscalErro("XML contém múltiplas famílias de documentos fiscais")
    if len(nfes) > 1 or len(ctes) > 1:
        raise XMLFiscalErro("Lotes de XML devem ser enviados como arquivos individuais")
    if nfes:
        return texto(filho(nfes[0], "ide"), "mod")
    if ctes:
        return texto(filho(ctes[0], "ide"), "mod")
    return "nfse_ou_desconhecido"


def interpretar(conteudo: bytes):
    modelo = detectar_modelo(conteudo)
    if modelo in ("55", "65", "57"):
        resultado = {"55": ler_nfe, "65": ler_nfce, "57": ler_cte}[modelo](conteudo)
        resultado["validacao"].update(validar_xsd(conteudo, modelo, resultado["versao"]))
        return resultado
    if modelo == "nfse_ou_desconhecido":
        return None  # conserva exatamente o parser de NFS-e existente
    raise XMLFiscalErro(f"Modelo fiscal não suportado: {modelo}")
