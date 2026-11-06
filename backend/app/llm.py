"""Leitura com o Claude (opcional). Liga quando LLM_API_KEY está preenchida no .env.

Para cada documento já separado pelo motor local, o Claude confirma o tipo e extrai os campos com a
página e o trecho de onde tirou cada valor. Campos que o Claude deixar vazios são completados pelas
regras locais. Sem chave, ou se a chamada falhar, vale só o resultado local: o lote nunca trava.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from typing import Callable

from app.config import get_settings
from app.intelligence import DOC_TYPES, _date, _money, extract_fields, normalized

log = logging.getLogger(__name__)
USO: list[dict] = []  # tokens de cada chamada, para medir custo
MAX_IMAGENS = 6  # imagens por documento (cada uma custa ~2 mil tokens)
IMAGEM_TETO = 0.7  # confiança máxima de página lida só pela imagem: abaixo de 0,75, vai para revisão

# Campos que a conferência (intelligence.reconcile) usa, por tipo.
CAMPOS = {
    "contrato": ["contract_id", "supplier_name", "supplier_cnpj", "buyer_cnpj", "service", "value", "validity"],
    "aditivo_contratual": ["amendment_id", "contract_id", "supplier_cnpj", "additional_value", "validity"],
    "nota_fiscal_servico": ["invoice_number", "supplier_name", "supplier_cnpj", "buyer_cnpj", "issued_at",
                            "competence", "service", "value", "contract_id"],
    "outros": [],
}
TODOS = ["contract_id", "amendment_id", "invoice_number", "supplier_name", "supplier_cnpj", "buyer_cnpj",
         "service", "value", "additional_value", "issued_at", "competence", "validity_start", "validity_end"]

_CAMPO = {"type": "object", "additionalProperties": False, "required": ["value", "page", "excerpt"],
          "properties": {"value": {"type": "string"}, "page": {"type": "integer"}, "excerpt": {"type": "string"}}}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["kind", "confidence", "reasons", "fields"],
    "properties": {
        "kind": {"type": "string", "enum": list(DOC_TYPES)},
        "confidence": {"type": "number"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "fields": {"type": "object", "additionalProperties": False, "required": TODOS,
                   "properties": {k: _CAMPO for k in TODOS}},
    },
}

PROMPT = """Você confere documentos de fornecedores terceirizados: contratos de prestação de serviços, termos aditivos e notas fiscais de serviço (NFS-e). O texto abaixo veio de OCR e pode ter erros. As páginas estão marcadas com <pagina n="...">.

1. kind: contrato, aditivo_contratual, nota_fiscal_servico ou outros.
2. confidence: de 0 a 1, calibrada. Fique abaixo de 0.75 se houver dúvida real sobre o tipo ou se o texto parecer misturar mais de um documento.
3. reasons: 1 a 3 frases curtas em português dizendo o que você observou.
4. fields: para cada campo, value + page (número da página de onde veio) + excerpt (trecho copiado exatamente do texto). Campo que não existe no documento: value "", page 0, excerpt "".
   - contract_id: número do contrato (ex.: CTR-001); em nota ou aditivo, o contrato referenciado.
   - amendment_id: número do aditivo. invoice_number: número da nota.
   - supplier_name / supplier_cnpj: a empresa contratada, que presta o serviço e emite a nota. buyer_cnpj: a contratante/tomadora.
   - service: objeto do contrato ou descrição do serviço da nota.
   - value: valor mensal do contrato ou valor do serviço da nota. additional_value: acréscimo mensal do aditivo.
   - issued_at: data de emissão da nota. competence: competência da nota (AAAA-MM).
   - validity_start / validity_end: vigência do contrato ou do aditivo.
   Datas em AAAA-MM-DD. Valores só com números e ponto decimal (ex.: 8000.00). CNPJ só com os 14 dígitos.

Classificação feita pelas regras locais (pode estar errada): {local}.

{paginas}"""


def ativo() -> bool:
    return bool(get_settings().llm_api_key.strip())


def ocr_fraco(p: dict) -> bool:
    """Página que o OCR quase não leu: vale mandar a imagem ao Claude."""
    return len((p.get("text") or "").strip()) < 30 or float(p.get("confidence") or 0) < 0.6


def _chamar(paginas: list[dict], tipo_local: str, imagens: dict[int, bytes] | None = None) -> dict:
    import anthropic

    s = get_settings()
    imagens = imagens or {}
    texto = "\n".join(f'<pagina n="{p["number"]}">\n{(p.get("text") or "")[:6000]}\n</pagina>' for p in paginas[:12])
    conteudo = []
    for n, png in imagens.items():
        conteudo.append({"type": "text", "text": f"Imagem da página {n} (o OCR leu pouco ou nada dela):"})
        conteudo.append({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                     "data": base64.standard_b64encode(png).decode()}})
    aviso = ("\n\nPara as páginas com imagem, leia a imagem; o excerpt deve copiar o que está escrito nela."
             if imagens else "")
    conteudo.append({"type": "text", "text": PROMPT.format(local=tipo_local, paginas=texto) + aviso})
    cliente = anthropic.Anthropic(api_key=s.llm_api_key.strip(), timeout=120, max_retries=2)
    pedido = dict(
        model=s.llm_model, max_tokens=4000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": conteudo}],
    )
    if s.llm_model.startswith("claude-haiku"):
        resp = cliente.messages.create(**pedido)  # Haiku não tem fallback no servidor
    else:
        # Se o modelo recusar, a própria API refaz o pedido em outro modelo.
        resp = cliente.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **pedido)
    USO.append({"modelo": resp.model, "entrada": resp.usage.input_tokens, "saida": resp.usage.output_tokens})
    del USO[:-1000]
    if resp.stop_reason in ("refusal", "max_tokens"):
        raise RuntimeError(f"resposta incompleta ({resp.stop_reason})")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


def _normalizar(campo: str, v: str):
    v = (v or "").strip()
    if not v:
        return None
    if campo.endswith("cnpj"):
        v = re.sub(r"\D", "", v)
        return v if len(v) == 14 else None
    if campo in ("value", "additional_value"):
        return _money(v)
    if campo in ("issued_at", "validity_start", "validity_end"):
        return _date(v)
    if campo in ("contract_id", "amendment_id"):
        return normalized(v).replace(" ", "")
    if campo == "invoice_number":
        return re.sub(r"\D", "", v) or None
    return v


def _compacto(texto: str) -> str:
    return re.sub(r"\s+", " ", normalized(texto)).strip()


def _campos(dados: dict, kind: str, paginas: list[dict], lidas_por_imagem: set[int] = frozenset()) -> dict:
    por_pagina = {int(p["number"]): p for p in paginas}

    def evidencia(bruto: dict, valor):
        p = por_pagina.get(int(bruto.get("page") or 0)) or paginas[0]
        trecho = (bruto.get("excerpt") or "").strip()[:240]
        if p["number"] in lidas_por_imagem:
            # Sem texto para conferir o trecho: valor útil, mas a revisão humana confirma.
            return {"value": valor, "page": p["number"], "excerpt": trecho, "confidence": IMAGEM_TETO,
                    "source": "claude_imagem"}
        conf = float(p.get("confidence") or 0)
        # Trecho que não está no texto da página: o valor pode ter sido inventado; baixa a confiança.
        if trecho and _compacto(trecho) not in _compacto(p.get("text") or ""):
            conf = min(conf, 0.5)
        return {"value": valor, "page": p["number"], "excerpt": trecho, "confidence": conf, "source": "claude"}

    out = {}
    brutos = dados.get("fields") or {}
    for campo in CAMPOS[kind]:
        if campo == "validity":
            ini = _normalizar("validity_start", brutos.get("validity_start", {}).get("value"))
            fim = _normalizar("validity_end", brutos.get("validity_end", {}).get("value"))
            if ini and fim:
                out["validity"] = evidencia(brutos["validity_start"], [ini, fim])
            continue
        bruto = brutos.get(campo) or {}
        valor = _normalizar(campo, bruto.get("value"))
        if valor is not None:
            out[campo] = evidencia(bruto, valor)
    return out


def analisar(paginas: list[dict], kind: str, confidence: float, reasons: list[str],
             imagem: Callable[[int], bytes] | None = None) -> tuple[str, float, list[str], dict]:
    """Tipo, confiança, motivos e campos de um documento já separado. Sempre devolve algo.

    imagem(n) devolve o PNG da página n; só é chamada para páginas que o OCR leu mal.
    """
    locais = extract_fields(paginas, kind)
    if not ativo() or not paginas:
        return kind, confidence, reasons, locais
    imagens: dict[int, bytes] = {}
    if imagem:
        for p in [p for p in paginas if ocr_fraco(p)][:MAX_IMAGENS]:
            try:
                imagens[int(p["number"])] = imagem(int(p["number"]))
            except Exception as e:  # arquivo indisponível: segue só com o texto
                log.warning("Imagem da página %s indisponível: %s", p["number"], e)
    try:
        dados = _chamar(paginas, kind, imagens)
    except Exception as e:  # rede, limite de uso, chave inválida, resposta estranha
        log.warning("Claude indisponível, usada a leitura local: %s", e)
        return kind, confidence, reasons + ["Claude indisponível; usada a leitura local"], locais

    novo = dados["kind"] if dados["kind"] in DOC_TYPES else kind
    # Página lida pela imagem conta como OCR razoável, mas nunca passa do teto: vai para revisão.
    ocr = min(IMAGEM_TETO if int(p["number"]) in imagens else float(p.get("confidence") or 0) for p in paginas)
    conf = min(max(0.0, min(1.0, float(dados["confidence"]))), max(0.05, ocr))
    motivos = ["Claude: " + r for r in dados.get("reasons", [])[:3]]
    if imagens:
        motivos.append(f"Claude leu a imagem de {len(imagens)} página(s) com OCR fraco")
    if novo != kind:
        # Regras e Claude discordam: quem decide é a revisão humana.
        conf = min(conf, 0.6)
        motivos.append(f"Regras locais diziam {kind}; Claude diz {novo}")
        locais = extract_fields(paginas, novo)
    campos = _campos(dados, novo, paginas, set(imagens))
    # Regra local com rótulo exato tem prioridade; o Claude completa o que ela não achou.
    campos.update(locais)
    return novo, round(conf, 3), list(dict.fromkeys(reasons + motivos)), campos
