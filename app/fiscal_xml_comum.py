"""Infraestrutura compartilhada para leitura determinística de DF-e.

Não executa resolução de entidades XML, OCR ou chamadas de IA.
"""
from __future__ import annotations

import re
import hashlib
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

MAX_XML_BYTES = 25 * 1024 * 1024


class XMLFiscalErro(ValueError):
    pass


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def filho(no, caminho: str):
    """Pesquisa apenas filhos diretos: evita capturar campos de grupos errados."""
    if no is None:
        return None
    for nome in caminho.split("/"):
        no = next((e for e in no if local(e.tag) == nome), None)
        if no is None:
            return None
    return no


def filhos(no, nome: str):
    return [e for e in no if local(e.tag) == nome] if no is not None else []


def texto(no, caminho: str) -> str | None:
    el = filho(no, caminho)
    return (el.text or "").strip() or None if el is not None else None


def decimal(no, caminho: str) -> str | None:
    v = texto(no, caminho)
    if v is None:
        return None
    try:
        d = Decimal(v)
        if not d.is_finite():
            raise ValueError()
        return str(d)
    except (InvalidOperation, ValueError):
        raise XMLFiscalErro("Valor decimal inválido em " + caminho)


def abrir(conteudo: bytes):
    if not conteudo or len(conteudo) > MAX_XML_BYTES:
        raise XMLFiscalErro("XML vazio ou acima do limite de 25 MB")
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", conteudo, re.I):
        raise XMLFiscalErro("DTD e entidades XML não são permitidas")
    try:
        return ET.fromstring(conteudo)
    except ET.ParseError as exc:
        raise XMLFiscalErro(f"XML malformado: {exc}") from None


def unico(raiz, tag: str):
    encontrados = [e for e in raiz.iter() if local(e.tag) == tag]
    if len(encontrados) != 1:
        raise XMLFiscalErro(f"Esperado um único elemento {tag}; encontrados {len(encontrados)}")
    return encontrados[0]


def guardar(origem: dict, campo: str, no, caminho: str, base: str):
    v = texto(no, caminho)
    if v is not None:
        origem[campo] = {"caminho_xml": f"{base}/{caminho}", "valor_original": v,
                         "metodo": "xml_deterministico", "origem": "extraido"}
    return v


def guardar_decimal(origem: dict, campo: str, no, caminho: str, base: str):
    v = decimal(no, caminho)
    if v is not None:
        origem[campo] = {"caminho_xml": f"{base}/{caminho}", "valor_original": texto(no, caminho),
                         "metodo": "xml_deterministico", "origem": "extraido"}
    return v


def protocolo(raiz, nome: str):
    prot = next((e for e in raiz.iter() if local(e.tag) == nome), None)
    inf = filho(prot, "infProt")
    codigo = texto(inf, "cStat")
    return {
        "codigo": codigo, "mensagem": texto(inf, "xMotivo"),
        "numero": texto(inf, "nProt"), "recebimento": texto(inf, "dhRecbto"),
        "autorizado": codigo in ("100", "150"),
        "verificado_na_sefaz": False,
    }


def resultado_base(modelo: str, tipo: str, versao: str | None, conteudo: bytes):
    return {
        "modelo": modelo, "tipo": tipo, "versao": versao,
        "sha256": hashlib.sha256(conteudo).hexdigest(),
        "campos": {}, "itens": [], "tributos": {}, "referencias": [],
        "proveniencia": {}, "avisos": [],
        "validacao": {
            "xml_bem_formado": True,
            "xsd": "nao_executada",
            "motivo_xsd": "Os esquemas oficiais específicos da versão ainda não estão configurados",
            "autorizacao_online": "nao_consultada",
        },
    }


def identificador(inf, prefixo: str):
    raw = inf.get("Id", "") or ""
    return raw[len(prefixo):] if raw.startswith(prefixo) else None


def chave_status(chave: str | None, modelo: str):
    if not chave or not re.fullmatch(r"\d{44}", chave):
        return "ausente_ou_invalida"
    if chave[20:22] != modelo:
        return "modelo_divergente"
    nums = [int(i) for i in chave[:43]][::-1]
    dv = (11 - sum(n * ((i % 8) + 2) for i, n in enumerate(nums)) % 11) % 11
    if dv >= 10:
        dv = 0
    return "valida" if dv == int(chave[-1]) else "digito_verificador_invalido"
