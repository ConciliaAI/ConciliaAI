"""Leitura dos documentos fiscais: XML da NFS-e e campos de contratos, aditivos e notas em PDF.

- XML: lê o leiaute nacional da NFS-e (NFSe/infNFSe/DPS) e o XML de demonstração do gerador sintético,
  procurando os campos pelo nome da tag (sem depender de namespace).
- PDF: o texto da página (do PDF ou do OCR) passa por regras de rótulo ("Valor mensal: ...").
  Com a chave do Claude, o texto vai também para o modelo, que devolve os campos em JSON.
"""
import json
import re
from datetime import date
from xml.etree import ElementTree

from . import config
from .analise import limpar_ocr, norm

TIPO_NOTA = "Nota fiscal de serviço"
TIPO_CONTRATO = "Contrato de prestação de serviços"
TIPO_ADITIVO = "Aditivo contratual"
TIPOS_FISCAIS = (TIPO_NOTA, TIPO_CONTRATO, TIPO_ADITIVO)


# ------------------------------------------------------------------ utilidades
def so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s or ""))


def cnpj_valido(cnpj) -> bool:
    d = so_digitos(cnpj)
    if len(d) != 14 or len(set(d)) == 1:
        return False
    for tam in (12, 13):
        pesos = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] if tam == 12 else [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
        resto = sum(int(a) * b for a, b in zip(d[:tam], pesos)) % 11
        if int(d[tam]) != (0 if resto < 2 else 11 - resto):
            return False
    return True


def fmt_cnpj(cnpj) -> str:
    d = so_digitos(cnpj)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else (cnpj or "")


def valor(s) -> float | None:
    """'R$ 4.000,00' -> 4000.0 ; '4000.00' -> 4000.0"""
    if s is None:
        return None
    t = re.sub(r"[^\d,.\-]", "", str(s))
    if not re.search(r"\d", t):
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1:
        t = t.replace(".", "")
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def brl(v) -> str:
    if v is None:
        return "—"
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


RE_DATA_BR = re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b")
RE_DATA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})")


def datas(s) -> list[str]:
    """Todas as datas do texto, em ordem, no formato AAAA-MM-DD."""
    achadas = []
    # Sem \b: o OCR cola palavras nas datas ("01/01/2026a 31/12/2026").
    for m in re.finditer(r"(?<!\d)\d{2}/\d{2}/\d{4}(?!\d)|(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)", str(s or "")):
        t = m.group(0)
        b = RE_DATA_BR.match(t)
        iso = f"{b.group(3)}-{b.group(2)}-{b.group(1)}" if b else t[:10]
        try:
            date.fromisoformat(iso)
            achadas.append(iso)
        except ValueError:
            pass
    return achadas


def data(s) -> str | None:
    d = datas(s)
    return d[0] if d else None


def competencia(s) -> str | None:
    t = str(s or "")
    m = re.search(r"\b(\d{4})-(\d{2})\b", t) or None
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = re.search(r"\b(\d{2})/(\d{4})\b", t)
    return f"{m.group(2)}-{m.group(1)}" if m else None


def fmt_data(iso) -> str:
    if not iso:
        return "—"
    try:
        d = date.fromisoformat(iso[:10])
        return d.strftime("%d/%m/%Y")
    except ValueError:
        return iso


# ------------------------------------------------------------------ XML da NFS-e
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _achar(raiz, nomes, dentro=None):
    """Texto da primeira tag com um dos nomes; se 'dentro', só procura sob uma tag com esse nome."""
    bases = [raiz]
    if dentro:
        bases = [el for el in raiz.iter() if _local(el.tag) in dentro]
    for base in bases:
        for nome in nomes:
            for el in base.iter():
                if _local(el.tag) == nome and (el.text or "").strip():
                    return el.text.strip()
    return None


def ler_nfse_xml(conteudo: bytes) -> dict:
    """Lê uma NFS-e em XML. Levanta ValueError se não parecer uma nota de serviço."""
    try:
        raiz = ElementTree.fromstring(conteudo)
    except ElementTree.ParseError as erro:
        raise ValueError(f"XML inválido ({erro})") from None
    nomes = {_local(el.tag) for el in raiz.iter()}
    nacional = bool({"infNFSe", "infDPS", "DPS"} & nomes)
    demo = _local(raiz.tag) == "NfseDemonstracao"
    abrasf = bool({"InfNfse", "CompNfse", "Nfse"} & nomes)
    if not (nacional or demo or abrasf):
        raise ValueError("não parece uma NFS-e (faltam as tags da nota)")

    chave = None
    for el in raiz.iter():
        if _local(el.tag) in ("infNFSe", "InfNfse") and el.get("Id"):
            chave = re.sub(r"^NFS", "", el.get("Id"))
    nota = {
        "chave": chave or _achar(raiz, ["chNFSe", "CodigoVerificacao"]),
        "numero": _achar(raiz, ["nNFSe", "numero", "Numero"]),
        "data_emissao": data(_achar(raiz, ["dhEmi", "dhProc", "data_emissao", "DataEmissao"])),
        "competencia": competencia(_achar(raiz, ["dCompet", "competencia", "Competencia"])),
        "cnpj_prestador": so_digitos(_achar(raiz, ["CNPJ", "Cnpj"], dentro={"emit", "prest", "Prestador", "PrestadorServico", "IdentificacaoPrestador"})
                                     or _achar(raiz, ["prestador_cnpj"])),
        "nome_prestador": _achar(raiz, ["xNome", "RazaoSocial"], dentro={"emit", "prest", "PrestadorServico"}) or _achar(raiz, ["prestador_nome"]),
        "cnpj_tomador": so_digitos(_achar(raiz, ["CNPJ", "Cnpj"], dentro={"toma", "Tomador", "TomadorServico", "IdentificacaoTomador"})
                                   or _achar(raiz, ["tomador_cnpj"])),
        "descricao": _achar(raiz, ["xDescServ", "descricao_servico", "Discriminacao"]),
        "codigo_servico": _achar(raiz, ["cTribNac", "ItemListaServico", "CodigoTributacaoMunicipio"]),
        "valor": valor(_achar(raiz, ["vServ", "valor_servico", "ValorServicos"])),
        "valor_liquido": valor(_achar(raiz, ["vLiq", "ValorLiquidoNfse"])),
        "contrato_ref": _achar(raiz, ["contrato", "xPed", "NumeroContrato"]),
        "formato": "NFS-e nacional" if nacional else ("XML de demonstração" if demo else "NFS-e municipal (ABRASF)"),
    }
    if nota["competencia"] is None and nota["data_emissao"]:
        nota["competencia"] = nota["data_emissao"][:7]
    falta = [k for k in ("numero", "cnpj_prestador", "valor") if not nota[k]]
    if falta:
        raise ValueError("faltam campos obrigatórios: " + ", ".join(falta))
    return nota


def nfse_nacional_xml(inv: dict, nome_prestador: str, nome_tomador: str = "Cliente Bernhoeft (demonstração)") -> bytes:
    """Monta uma NFS-e fictícia no leiaute nacional v1.01 (valida no XSD oficial NFSe_v1.01.xsd).

    Os dados são do gerador sintético; a assinatura digital é um marcador (não é uma assinatura válida)."""
    ns, ds = "http://www.sped.fazenda.gov.br/nfse", "http://www.w3.org/2000/09/xmldsig#"
    ElementTree.register_namespace("", ns)
    E = lambda tag, attrs=None: ElementTree.Element(f"{{{ns}}}{tag}", attrs or {})
    def S(pai, tag, texto=None, attrs=None, espaco=ns):
        el = ElementTree.SubElement(pai, f"{{{espaco}}}{tag}", attrs or {})
        if texto is not None:
            el.text = str(texto)
        return el
    cmun = "2606002"  # Garanhuns/PE (IBGE)
    cnpj = so_digitos(inv["prestador_cnpj"])
    numero = str(int(so_digitos(inv["numero"]) or 1))
    seq = so_digitos(inv.get("invoice_id", ""))[-6:].rjust(6, "0")
    data, valor = inv["data_emissao"], f"{float(inv['valor_servico']):.2f}"
    # Chave de 50 dígitos: município + ambiente + tipo de inscrição + CNPJ + número + AAMM + código + DV (fictícios).
    chave = cmun + "1" + "2" + cnpj + numero.rjust(13, "0") + data[2:4] + data[5:7] + ("000" + seq) + "0"
    id_dps = cmun + "2" + cnpj + "00001" + numero.rjust(15, "0")

    raiz = E("NFSe", {"versao": "1.01"})
    inf = S(raiz, "infNFSe", attrs={"Id": "NFS" + chave})
    S(inf, "xLocEmi", "Garanhuns")
    S(inf, "xLocPrestacao", "Garanhuns")
    S(inf, "nNFSe", numero)
    S(inf, "xTribNac", "Limpeza, manutenção e conservação de imóveis")
    S(inf, "verAplic", "ConciliaAI-demo")
    S(inf, "ambGer", "2")
    S(inf, "tpEmis", "1")
    S(inf, "cStat", "100")
    S(inf, "dhProc", data + "T09:00:00-03:00")
    S(inf, "nDFSe", numero)
    emit = S(inf, "emit")
    S(emit, "CNPJ", cnpj)
    S(emit, "xNome", nome_prestador[:150])
    end = S(emit, "enderNac")
    for tag, v in (("xLgr", "Rua Exemplo"), ("nro", "100"), ("xBairro", "Centro"), ("cMun", cmun), ("UF", "PE"), ("CEP", "55290000")):
        S(end, tag, v)
    S(S(inf, "valores"), "vLiq", valor)
    dps = S(S(inf, "DPS", attrs={"versao": "1.01"}), "infDPS", attrs={"Id": "DPS" + id_dps})
    S(dps, "tpAmb", "2")
    S(dps, "dhEmi", data + "T08:00:00-03:00")
    S(dps, "verAplic", "ConciliaAI-demo")
    S(dps, "serie", "1")
    S(dps, "nDPS", numero)
    S(dps, "dCompet", data)
    S(dps, "tpEmit", "1")
    S(dps, "cLocEmi", cmun)
    prest = S(dps, "prest")
    S(prest, "CNPJ", cnpj)
    reg = S(prest, "regTrib")
    S(reg, "opSimpNac", "3")  # optante do Simples Nacional (ME/EPP)
    S(reg, "regEspTrib", "0")
    toma = S(dps, "toma")
    S(toma, "CNPJ", so_digitos(inv["tomador_cnpj"]))
    S(toma, "xNome", nome_tomador[:150])
    serv = S(dps, "serv")
    S(S(serv, "locPrest"), "cLocPrestacao", cmun)
    c = S(serv, "cServ")
    S(c, "cTribNac", "070101")
    S(c, "xDescServ", inv["descricao_servico"])
    vals = S(dps, "valores")
    S(S(vals, "vServPrest"), "vServ", valor)
    trib = S(vals, "trib")
    tm = S(trib, "tribMun")
    S(tm, "tribISSQN", "1")
    S(tm, "tpRetISSQN", "1")
    S(S(trib, "totTrib"), "pTotTribSN", "6.00")
    # Marcador no lugar da assinatura digital do Sistema Nacional (o esquema exige o bloco).
    sig = S(raiz, "Signature", espaco=ds)
    si = S(sig, "SignedInfo", espaco=ds)
    S(si, "CanonicalizationMethod", attrs={"Algorithm": "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"}, espaco=ds)
    S(si, "SignatureMethod", attrs={"Algorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"}, espaco=ds)
    ref = S(si, "Reference", attrs={"URI": "#NFS" + chave}, espaco=ds)
    S(ref, "DigestMethod", attrs={"Algorithm": "http://www.w3.org/2001/04/xmlenc#sha256"}, espaco=ds)
    S(ref, "DigestValue", "QVNTSU5BVFVSQS1GSUNUSUNJQQ==", espaco=ds)
    S(sig, "SignatureValue", "QVNTSU5BVFVSQS1GSUNUSUNJQQ==", espaco=ds)
    return b'<?xml version="1.0" encoding="UTF-8"?>\n' + ElementTree.tostring(raiz, encoding="utf-8")


# ------------------------------------------------------------- campos em PDF
ROTULOS = {
    TIPO_CONTRATO: {
        "numero": ["instrumento", "numero do contrato", "contrato n", "contrato no", "contrato nº"],
        "nome_prestador": ["contratada", "razao social da contratada"],
        "cnpj_prestador": ["cnpj contratada", "cnpj da contratada"],
        "cnpj_tomador": ["cnpj contratante", "cnpj da contratante"],
        "objeto": ["objeto", "objeto do contrato"],
        "valor_mensal": ["valor mensal", "valor mensal do contrato"],
        "valor_total": ["valor global", "valor total do contrato", "valor total"],
        "vigencia": ["vigencia", "prazo de vigencia", "periodo de vigencia"],
    },
    TIPO_ADITIVO: {
        "numero": ["aditivo", "termo aditivo n", "numero do aditivo"],
        "contrato_ref": ["contrato", "contrato original"],
        "cnpj_prestador": ["fornecedor", "cnpj", "cnpj contratada"],
        "valor_adicional": ["acrescimo mensal", "valor do acrescimo", "valor adicional"],
        "vigencia": ["vigencia do aditivo", "vigencia"],
    },
    TIPO_NOTA: {
        "numero": ["numero da nfs-e", "numero da nota", "numero", "n da nfs-e"],
        "nome_prestador": ["prestador", "razao social do prestador", "emitente"],
        "cnpj_prestador": ["cnpj prestador", "cnpj do prestador", "cnpj emitente"],
        "cnpj_tomador": ["cnpj tomador", "cnpj do tomador"],
        "data_emissao": ["data emissao", "data de emissao", "data e hora da emissao"],
        "competencia": ["competencia", "competencia da nfs-e"],
        "descricao": ["descricao", "descricao do servico", "discriminacao do servico"],
        "valor": ["valor do servico", "valor dos servicos", "valor total da nota"],
        "contrato_ref": ["contrato referenciado", "contrato"],
    },
}


def _rotulados(texto: str, rotulos: dict) -> dict:
    """Para cada campo, o valor da primeira linha 'Rótulo: valor' (texto original, sem acento só na busca)."""
    achados = {}
    linhas = limpar_ocr(texto or "").splitlines()
    # Compara sem espaços: o OCR de página digitalizada cola palavras ("Valormensal:", "CNPJcontratada:").
    chaves = [(re.sub(r"\s+", "", norm(ln)), ln) for ln in linhas if ":" in ln]
    for campo, nomes in rotulos.items():
        for nome in sorted(nomes, key=len, reverse=True):
            alvo = re.sub(r"\s+", "", nome) + ":"
            for chave, ln in chaves:
                if chave.startswith(alvo):
                    v = ln.split(":", 1)[1].strip(" .;")
                    if v:
                        achados[campo] = v
                        break
            if campo in achados:
                break
    return achados


RE_CNPJ = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")


def extrair_local(tipo: str, texto: str) -> dict:
    r = _rotulados(texto, ROTULOS.get(tipo, {}))
    out = {}
    if tipo == TIPO_CONTRATO:
        vig = datas(r.get("vigencia"))
        out = {"numero": r.get("numero"), "nome_prestador": r.get("nome_prestador"),
               "cnpj_prestador": so_digitos(r.get("cnpj_prestador")), "cnpj_tomador": so_digitos(r.get("cnpj_tomador")),
               "objeto": r.get("objeto"), "valor_mensal": valor(r.get("valor_mensal")), "valor_total": valor(r.get("valor_total")),
               "vigencia_inicio": vig[0] if len(vig) > 1 else None, "vigencia_fim": vig[1] if len(vig) > 1 else None}
    elif tipo == TIPO_ADITIVO:
        vig = datas(r.get("vigencia"))
        out = {"numero": r.get("numero"), "contrato_ref": r.get("contrato_ref"),
               "cnpj_prestador": so_digitos((RE_CNPJ.search(r.get("cnpj_prestador") or "") or [None])[0] if r.get("cnpj_prestador") else None),
               "valor_adicional": valor(r.get("valor_adicional")),
               "vigencia_inicio": vig[0] if len(vig) > 1 else None, "vigencia_fim": vig[1] if len(vig) > 1 else None}
    elif tipo == TIPO_NOTA:
        out = {"numero": so_digitos(r.get("numero")) or r.get("numero"), "nome_prestador": r.get("nome_prestador"),
               "cnpj_prestador": so_digitos(r.get("cnpj_prestador")), "cnpj_tomador": so_digitos(r.get("cnpj_tomador")),
               "data_emissao": data(r.get("data_emissao")), "competencia": competencia(r.get("competencia")),
               "descricao": r.get("descricao"), "valor": valor(r.get("valor")), "contrato_ref": r.get("contrato_ref")}
        if out["contrato_ref"] and "nao informado" in norm(out["contrato_ref"]):
            out["contrato_ref"] = None
    # CNPJs sem rótulo: o primeiro diferente do tomador vira o do prestador.
    if tipo in (TIPO_CONTRATO, TIPO_NOTA) and not out.get("cnpj_prestador"):
        todos = [so_digitos(c) for c in RE_CNPJ.findall(texto or "")]
        outros = [c for c in todos if c != out.get("cnpj_tomador")]
        out["cnpj_prestador"] = outros[0] if outros else None
    return {k: v for k, v in out.items() if v not in (None, "")}


def _schema(tipo: str) -> dict:
    campos = {
        TIPO_CONTRATO: ["numero", "nome_prestador", "cnpj_prestador", "cnpj_tomador", "objeto", "valor_mensal",
                        "valor_total", "vigencia_inicio", "vigencia_fim"],
        TIPO_ADITIVO: ["numero", "contrato_ref", "cnpj_prestador", "valor_adicional", "vigencia_inicio", "vigencia_fim"],
        TIPO_NOTA: ["numero", "nome_prestador", "cnpj_prestador", "cnpj_tomador", "data_emissao", "competencia",
                    "descricao", "valor", "contrato_ref"],
    }[tipo]
    return {"type": "object", "properties": {c: {"type": "string"} for c in campos},
            "required": campos, "additionalProperties": False}


def extrair_claude(tipo: str, texto: str) -> dict:
    import anthropic

    prompt = f"""Extraia os campos deste documento ({tipo}) de um fornecedor terceirizado.
Regras: copie os valores como aparecem no documento. Datas no formato AAAA-MM-DD. Valores em reais só com números e ponto decimal (ex.: 4800.00).
CNPJ só com os 14 dígitos. Competência no formato AAAA-MM. Use texto vazio quando o campo não existir no documento.
cnpj_prestador é o da empresa contratada (quem presta o serviço e emite a nota); cnpj_tomador é o da contratante.

<documento>
{(texto or '')[:12000]}
</documento>"""
    resp = anthropic.Anthropic().messages.create(
        model=config.MODELO, max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _schema(tipo)}},
        messages=[{"role": "user", "content": prompt}])
    from .analise import registrar_uso
    registrar_uso("extracao", resp)
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"resposta incompleta ({resp.stop_reason})")
    d = json.loads(next(b.text for b in resp.content if b.type == "text"))
    out = {}
    for k, v in d.items():
        v = (v or "").strip()
        if not v:
            continue
        if k.startswith("cnpj"):
            v = so_digitos(v)
        elif k.startswith("valor"):
            v = valor(v)
        elif k in ("data_emissao", "vigencia_inicio", "vigencia_fim"):
            v = data(v)
        elif k == "competencia":
            v = competencia(v)
        if v not in (None, ""):
            out[k] = v
    return out


def extrair(tipo: str, texto: str, usar_claude: bool = False) -> tuple[dict, str]:
    """Campos do documento e o motor usado. Regras locais preenchem o que o Claude deixar vazio."""
    local = extrair_local(tipo, texto)
    if usar_claude and config.claude_configurado():
        try:
            dados = extrair_claude(tipo, texto)
            for k, v in local.items():
                dados.setdefault(k, v)
            return dados, "claude"
        except Exception:
            pass
    return local, "local"
