"""Validação opcional por XSDs oficiais locais; não equivale à consulta à SEFAZ.

Configure CONCILIA_XSD_DIR com o pacote oficial descompactado (incluindo imports).
Um esquema não configurado é sempre 'não executado', jamais 'válido'.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from xml.etree import ElementTree

from .fiscal_xml_comum import XMLFiscalErro, local


def validar_xsd(conteudo: bytes, modelo: str, versao: str | None) -> dict:
    pasta = os.environ.get("CONCILIA_XSD_DIR", "").strip()
    if not pasta:
        return {"xsd": "nao_executada", "motivo_xsd": "CONCILIA_XSD_DIR não configurado"}
    if not versao or not re.fullmatch(r"\d{1,2}\.\d{2}", versao):
        return {"xsd": "nao_executada", "motivo_xsd": "Versão XML ausente ou desconhecida"}
    try:
        raiz = ElementTree.fromstring(conteudo)
        tag = local(raiz.tag)
    except ElementTree.ParseError as exc:
        return {"xsd": "reprovada", "motivo_xsd": f"XML inválido: {exc}"}
    tipos = {"55": {"NFe": "nfe", "nfeProc": "procNFe"},
             "65": {"NFe": "nfe", "nfeProc": "procNFe"},
             "57": {"CTe": "cte", "cteProc": "procCTe"}}
    schema = tipos.get(modelo, {}).get(tag)
    if not schema:
        return {"xsd": "nao_executada", "motivo_xsd": "Raiz XML não mapeada para o modelo"}
    caminho = Path(pasta) / f"{schema}_v{versao}.xsd"
    if not caminho.is_file():
        return {"xsd": "nao_executada", "motivo_xsd": f"Esquema oficial ausente: {caminho.name}"}
    try:
        from lxml import etree
    except ImportError:
        return {"xsd": "nao_executada", "motivo_xsd": "Instale lxml para validar XSD"}
    try:
        parser = etree.XMLParser(resolve_entities=False, load_dtd=False,
                                 no_network=True, huge_tree=False)
        xml = etree.fromstring(conteudo, parser=parser)
        schema_xml = etree.parse(str(caminho), parser=parser)
        xsd = etree.XMLSchema(schema_xml)
        if not xsd.validate(xml):
            e = xsd.error_log.last_error
            return {"xsd": "reprovada", "motivo_xsd": str(e)[:350] if e else "XML fora do leiaute XSD"}
        return {"xsd": "aprovada", "motivo_xsd": f"Esquema local {caminho.name}"}
    except (OSError, etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        return {"xsd": "erro_validacao", "motivo_xsd": str(exc)[:350]}
