"""Motor local e determinístico do MVP Essencial.

Sem LLM, sem consulta fiscal. Scores heurísticos não são probabilidades calibradas.
As evidências guardam trecho e número de página original.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
import unicodedata

DOC_TYPES = ("contrato", "nota_fiscal_servico", "aditivo_contratual", "outros")


def normalized(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text or "") if not unicodedata.combining(c)).upper()


def classify(text: str) -> tuple[str, float, list[str]]:
    t = normalized(text[:3500])
    if not t.strip():
        return "outros", 0.05, ["Sem texto reconhecido"]
    patterns = [
        ("aditivo_contratual", [r"TERMO\s+ADITIVO", r"ADITIVO\s+CONTRATUAL", r"ACRESCIMO\s+MENSAL"]),
        ("nota_fiscal_servico", [r"NOTA\s+FISCAL", r"DANFSE?", r"VALOR\s+DO\s+SERVICO", r"DATA\s+EMISSAO"]),
        ("contrato", [r"CONTRATO\s+DE", r"CONTRATADA\s*:", r"VALOR\s+MENSAL", r"OBJETO\s*:"]),
    ]
    scores = [(kind, sum(bool(re.search(p, t)) for p in pats)) for kind, pats in patterns]
    scores.sort(key=lambda x: x[1], reverse=True)
    kind, hits = scores[0]
    if not hits:
        return "outros", 0.3, ["Sem cabeçalhos reconhecidos"]
    if len(scores) > 1 and scores[1][1] == hits:
        return kind, 0.5, ["Cabeçalhos ambíguos"]
    return kind, min(0.98, 0.62 + .12 * hits), [f"{hits} sinal(is) de {kind}"]


PAGE_MARKER = re.compile(r"\bPAGINA\s*(\d{1,4})\s*DE\s*(\d{1,4})\b")
DOC_ID = re.compile(r"\b(?:INSTRUMENTO|ADITIVO|CONTRATO REFERENCIADO)\s*:\s*((?:CTR|ADT)-\d{3})", re.I)
INVOICE_ID = re.compile(r"\bNUMERO\s*:\s*(\d{3,})\b")


def _identity(text: str, kind: str) -> str | None:
    t = normalized(text)
    if kind == "nota_fiscal_servico":
        m = INVOICE_ID.search(t)
        return m.group(1) if m else None
    if kind == "aditivo_contratual":
        m = re.search(r"\bADITIVO\s*:\s*(ADT-\d+)", t)
        return m.group(1) if m else None
    if kind == "contrato":
        m = re.search(r"\bINSTRUMENTO\s*:\s*(CTR-\d+)", t)
        return m.group(1) if m else None
    return None


@dataclass
class Group:
    start: int
    end: int
    kind: str
    confidence: float
    reasons: list[str]


def segment(pages: list[dict]) -> list[Group]:
    """Lista ordenada de páginas de UM arquivo de origem (não mistura arquivos)."""
    if not pages:
        return []
    groups: list[Group] = []
    start = 0
    prev_marker = None
    prev_kind = None
    prev_ident = None
    boundary_evidence = ["Primeira página do arquivo"]
    for idx, page in enumerate(pages):
        txt = page.get("text") or ""
        nt = normalized(txt)
        kind, conf, _ = classify(txt)
        marker_match = PAGE_MARKER.search(nt)
        marker = (int(marker_match.group(1)), int(marker_match.group(2))) if marker_match else None
        ident = _identity(txt, kind)
        reasons = []
        if idx:
            if marker and marker[0] == 1:
                reasons.append("Numeração reiniciada em página 1")
            if prev_marker and marker and marker[0] <= prev_marker[0]:
                reasons.append("Sequência da paginação reiniciada")
            if ident and prev_ident and ident != prev_ident and kind == prev_kind:
                reasons.append("Identificador documental mudou")
            if kind != "outros" and prev_kind != "outros" and kind != prev_kind:
                reasons.append("Tipo documental mudou")
            # Sem sinais confiáveis: evita dividir por mera presença de cabeçalho repetido.
            if reasons:
                subset = pages[start:idx]
                gkind, gconf, greasons = classify("\n".join(p.get("text") or "" for p in subset[:2]))
                ocr = min(float(p.get("confidence") or 0) for p in subset)
                evidence = list(dict.fromkeys(boundary_evidence + greasons))
                groups.append(Group(int(subset[0]["number"]), int(subset[-1]["number"]), gkind,
                                    round(min(gconf, max(.05, ocr)), 3), evidence))
                start = idx
                boundary_evidence = reasons
        if kind != "outros":
            prev_kind = kind
        if ident:
            prev_ident = ident
        prev_marker = marker
    subset = pages[start:]
    gkind, gconf, greasons = classify("\n".join(p.get("text") or "" for p in subset[:2]))
    ocr = min(float(p.get("confidence") or 0) for p in subset)
    groups.append(Group(int(subset[0]["number"]), int(subset[-1]["number"]), gkind,
                        round(min(gconf, max(.05, ocr)), 3), list(dict.fromkeys(boundary_evidence + greasons))))
    return groups


def _capture(text: str, label: str, value_pattern: str = r"([^\n\r]+)") -> tuple[str | None, str | None]:
    match = re.search(r"(?:^|\n)\s*" + label + r"\s*:\s*" + value_pattern, text, re.I)
    if not match:
        return None, None
    return match.group(1).strip(), match.group(0).strip()[:240]


def _money(value: str | None) -> str | None:
    if not value:
        return None
    value = re.sub(r"[^0-9,.-]", "", value)
    if not value:
        return None
    if "," in value:
        value = value.replace(".", "").replace(",", ".")
    try:
        return str(Decimal(value).quantize(Decimal("0.01")))
    except InvalidOperation:
        return None


def _date(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(v, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def extract_fields(pages: list[dict], kind: str) -> dict:
    """Cada campo: value + evidência com página/trecho. Sem inferir ausências."""
    if kind == "contrato":
        mapping = {"contract_id": r"Instrumento", "supplier_name": r"Contratada", "supplier_cnpj": r"CNPJ\s+contratada", "buyer_cnpj": r"CNPJ\s+contratante", "service": r"Objeto", "value": r"Valor\s+mensal", "validity": r"Vigencia"}
    elif kind == "aditivo_contratual":
        mapping = {"amendment_id": r"Aditivo", "contract_id": r"Contrato", "supplier_cnpj": r"Fornecedor", "additional_value": r"Acrescimo\s+mensal", "validity": r"Vigencia\s+do\s+aditivo"}
    elif kind == "nota_fiscal_servico":
        mapping = {"invoice_number": r"Numero", "supplier_name": r"Prestador", "supplier_cnpj": r"CNPJ\s+prestador", "buyer_cnpj": r"CNPJ\s+tomador", "issued_at": r"Data\s+emissao", "competence": r"Competencia", "service": r"Descricao", "value": r"Valor\s+do\s+servico", "contract_id": r"Contrato\s+referenciado"}
    else:
        return {}
    out = {}
    for key, label in mapping.items():
        for page in pages:
            value, snippet = _capture(normalized(page.get("text") or ""), label)
            if value is None:
                continue
            if key in ("value", "additional_value"):
                value = _money(value)
            elif key == "issued_at":
                value = _date(value)
            elif key == "validity":
                start, _, end = value.partition(" ATE " if " ATE " in value else " A ")
                value = [_date(start), _date(end)]
            elif key in ("supplier_cnpj", "buyer_cnpj"):
                value = re.sub(r"\D", "", value)
            if value is not None:
                out[key] = {"value": value, "page": page["number"], "excerpt": snippet, "confidence": float(page.get("confidence") or 0)}
                break
    return out


def value(fields: dict, name: str):
    return (fields.get(name) or {}).get("value")


def reconcile(documents: list[dict]) -> list[dict]:
    """Recebe documentos com id/kind/fields. Aplica regras rastreáveis.

    Premissa: comparação de mensalidade vs uma nota por competência é demonstrativa,
    não é adequada a faturamento por medição/unitário sem configuração adicional.
    """
    contracts = [d for d in documents if d["kind"] == "contrato"]
    amendments = [d for d in documents if d["kind"] == "aditivo_contratual"]
    invoices = [d for d in documents if d["kind"] == "nota_fiscal_servico"]
    findings = []
    seen = set()

    def finding(invoice, rule, severity, message, expected=None, observed=None, evidence=None, contract=None, status="divergencia"):
        findings.append({"invoice_id": invoice["id"], "contract_id": contract["id"] if contract else None,
                         "rule": rule, "severity": severity, "status": status, "message": message,
                         "expected": str(expected) if expected is not None else None,
                         "observed": str(observed) if observed is not None else None,
                         "evidence": evidence or []})

    for inv in invoices:
        f = inv["fields"]
        cnpj = value(f, "supplier_cnpj")
        buyer = value(f, "buyer_cnpj")
        target = value(f, "contract_id")
        relevant = [c for c in contracts if value(c["fields"], "supplier_cnpj") == cnpj and
                    (not buyer or value(c["fields"], "buyer_cnpj") == buyer)]
        if target and normalized(str(target)) not in ("NAO INFORMADO", "NONE"):
            relevant = [c for c in relevant if value(c["fields"], "contract_id") == target]
        if len(relevant) != 1:
            finding(inv, "SEM_CONTRATO" if not relevant else "MULTIPLOS_CONTRATOS", "alta",
                    "Contrato não identificado com segurança" if not relevant else "Há mais de um contrato possível",
                    observed=cnpj, evidence=[{"document_id": inv["id"], "field": "supplier_cnpj", **f.get("supplier_cnpj", {})}])
            continue
        contract = relevant[0]
        cf = contract["fields"]
        issue = value(f, "issued_at")
        validity = value(cf, "validity")
        if issue and validity and all(validity) and not (validity[0] <= issue <= validity[1]):
            finding(inv, "R05_FORA_VIGENCIA", "alta", "Emissão fora da vigência do contrato", validity, issue,
                    [{"document_id": contract["id"], "field": "validity", **cf["validity"]},
                     {"document_id": inv["id"], "field": "issued_at", **f["issued_at"]}], contract)
        num = value(f, "invoice_number")
        signature = (cnpj, num)
        if num and signature in seen:
            finding(inv, "R07_DUPLICADA", "alta", "Número de nota repetido para este prestador", num, num,
                    [{"document_id": inv["id"], "field": "invoice_number", **f["invoice_number"]}], contract)
        if num:
            seen.add(signature)
        expected = _money(value(cf, "value"))
        observed = _money(value(f, "value"))
        if not expected or not observed:
            finding(inv, "R09_CAMPO_AUSENTE", "media", "Valor não extraído com segurança", expected, observed,
                    [{"document_id": inv["id"], "field": "value", **f.get("value", {})}], contract)
        elif Decimal(observed) != Decimal(expected):
            delta = Decimal(observed) - Decimal(expected)
            justifying = []
            for a in amendments:
                af = a["fields"]
                av = value(af, "validity")
                if value(af, "contract_id") == value(cf, "contract_id") and av and all(av) and issue and av[0] <= issue <= av[1] and value(af, "additional_value") and Decimal(value(af, "additional_value")) == delta:
                    justifying.append(a)
            if len(justifying) == 1:
                a = justifying[0]
                finding(inv, "R02_ADITIVO", "baixa", "Diferença amparada por aditivo vigente; verificar manualmente", expected, observed,
                        [{"document_id": inv["id"], "field": "value", **f["value"]},
                         {"document_id": contract["id"], "field": "value", **cf["value"]},
                         {"document_id": a["id"], "field": "additional_value", **a["fields"]["additional_value"]}], contract, "justificada_pendente_validacao")
            else:
                finding(inv, "R02_VALOR", "alta", "Valor faturado diferente do mensal contratado sem aditivo aplicável identificado", expected, observed,
                        [{"document_id": inv["id"], "field": "value", **f["value"]},
                         {"document_id": contract["id"], "field": "value", **cf["value"]}], contract)
        svc_a, svc_b = value(f, "service"), value(cf, "service")
        if svc_a and svc_b:
            words_a = set(re.findall(r"[A-Z]{4,}", normalized(svc_a)))
            words_b = set(re.findall(r"[A-Z]{4,}", normalized(svc_b)))
            if words_a and words_b and len(words_a & words_b) / max(1, len(words_a | words_b)) < .25:
                finding(inv, "R04_SERVICO", "media", "Descrição do serviço possivelmente incompatível", svc_b, svc_a,
                        [{"document_id": inv["id"], "field": "service", **f["service"]},
                         {"document_id": contract["id"], "field": "service", **cf["service"]}], contract)
    return findings
