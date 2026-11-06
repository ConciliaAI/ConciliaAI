"""Decide, página a página: tipo do documento, se começa um documento novo e a confiança.

Dois motores:
- local: regras e palavras-chave sobre o texto lido (funciona sem internet e sem chave);
- Claude: lê a imagem e o texto juntos (multimodal). Usado quando há ANTHROPIC_API_KEY.
Se o Claude falhar, a página cai no motor local e isso fica registrado nos sinais.
"""
import base64
import io
import json
import re
import unicodedata

from PIL import Image

from . import config


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


RE_CPF = re.compile(r"\b(\d{3}\.\d{3}\.\d{3}-\d{2})\b")
RE_PESSOA = re.compile(r"(?im)^\s*(?:nome(?: do colaborador| do empregado| do funcion[aá]rio)?|colaborador|empregado|funcion[aá]rio|trabalhador|paciente|favorecido)\s*[:\-]\s*([A-ZÀ-Ü][A-Za-zÀ-ü.' ]{3,60})")
RE_EMPRESA_NOME = re.compile(r"(?i)\b(ME|LTDA|S\.?A\.?|EIRELI|EPP)\b")


def chave_nome(s: str) -> str:
    """Nome sem acento, pontuação e espaços: junta grafias diferentes (texto do PDF e do OCR)."""
    return re.sub(r"[^a-z0-9]", "", norm(s or ""))
RE_EMPRESA = re.compile(r"(?im)(?:empresa(?: contratada)?|empregador|raz[aã]o social|contratada)\s*[:\-]\s*([^\n]{3,70}?)(?:\s{2,}|\s+CNPJ|$)")
RE_PAG = re.compile(r"(?i)\b(?:p[aá]gina|p[aá]g\.?|folha|fls?\.?)\s*(\d{1,3})\s*(?:de|/)\s*(\d{1,3})\b")


def limpar_ocr(texto: str) -> str:
    """O OCR às vezes troca espaço por ponto ("Pedro.Henrique", "ME.CNPJ")."""
    t = re.sub(r"(?<=[A-Za-zÀ-ü])[.\-](?=[A-Za-zÀ-ü]{2})", " ", texto or "")
    return re.sub(r"[ \t]*:[ \t.:;,]*", ": ", t)


def extrair_basico(texto: str):
    texto = limpar_ocr(texto)
    cpf = RE_CPF.search(texto or "")
    pes = RE_PESSOA.search(texto or "")
    emp = RE_EMPRESA.search(texto or "")
    pag = RE_PAG.search(texto or "")
    return {
        "cpf": cpf.group(1) if cpf else None,
        "pessoa": " ".join(pes.group(1).split()).strip(" .") if pes else None,
        "empresa": " ".join(emp.group(1).split()).strip(" .:;,-") if emp else None,
        "pag": (int(pag.group(1)), int(pag.group(2))) if pag else None,
    }


def palavras(texto: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", norm(texto))}


# ---------------------------------------------------------------- motor local
def analisar_local(texto: str, tipos: list[dict], anterior: dict | None, exemplos: list[dict]) -> dict:
    t = norm(texto)
    topo = t[: max(300, len(t) // 4)]
    pal = palavras(texto)
    pontos = []
    for tp in tipos:
        s, titulo = 0.0, False
        for k in tp["titulos"]:
            if norm(k) in topo:
                s += 4
                titulo = True
            elif norm(k) in t:
                s += 1.5
        for k in tp["palavras"]:
            if norm(k) in t:
                s += 1
        pontos.append([tp["nome"], s, titulo])
    for ex in exemplos:
        ep = set(json.loads(ex["palavras"]))
        if ep and pal:
            jac = len(ep & pal) / len(ep | pal)
            if jac > 0.35:
                for p in pontos:
                    if p[0] == ex["tipo"]:
                        p[1] += 5 * jac
    pontos.sort(key=lambda p: -p[1])
    melhor, segundo = pontos[0], pontos[1] if len(pontos) > 1 else ["", 0, False]
    b = extrair_basico(texto)
    sinais = []
    qualidade = len(t.strip())

    if melhor[1] <= 0:
        tipo, conf = "Não identificado", 30
        sinais.append("Texto: nenhuma palavra típica de um tipo conhecido")
    else:
        tipo = melhor[0]
        margem = melhor[1] - segundo[1]
        conf = 58 + 9 * margem + (12 if melhor[2] else 0)
        if melhor[2]:
            sinais.append(f"Texto: título de “{tipo}” no topo da página")
        else:
            sinais.append(f"Texto: palavras típicas de “{tipo}”, sem título claro")
        if margem < 1.5 and segundo[1] > 0:
            sinais.append(f"Dúvida: também parece “{segundo[0]}”")
    if qualidade < 120:
        conf -= 22
        sinais.append("Imagem: pouco texto legível na página")

    inicio = anterior is None
    if anterior is None:
        sinais.append("Primeira página do envio")
    elif b["pag"]:
        inicio = b["pag"][0] == 1
        sinais.append(f"Numeração: “{b['pag'][0]} de {b['pag'][1]}”")
        if not inicio:
            if anterior.get("tipo") and tipo != anterior["tipo"]:
                tipo = anterior["tipo"]
                sinais.append("Continua o documento anterior pela numeração")
            conf = max(conf, 88)
        if not inicio and b["cpf"] and anterior.get("cpf") and b["cpf"] != anterior["cpf"]:
            conf -= 25
            sinais.append("Conflito: a numeração continua, mas o CPF mudou")
    else:
        if melhor[2]:
            inicio = True
        elif tipo != anterior.get("tipo") and melhor[1] > 0:
            inicio = True
            sinais.append("Tipo diferente da página anterior")
        if b["cpf"] and anterior.get("cpf") and b["cpf"] != anterior["cpf"]:
            inicio = True
            sinais.append("Pessoa: CPF diferente da página anterior")
        if not inicio:
            if tipo == "Não identificado":
                tipo, conf = anterior.get("tipo") or tipo, 62
            sinais.append("Continua o documento anterior (sem novo título nem nova numeração)")

    total = sum(max(p[1], 0) for p in pontos[:3]) or 1
    candidatos = [[p[0], round(100 * max(p[1], 0) / total)] for p in pontos[:3] if p[1] > 0]
    return {
        "tipo": tipo, "conf": int(max(15, min(99, conf))), "inicio": bool(inicio), "sinais": sinais,
        "candidatos": candidatos, "pessoa": b["pessoa"], "cpf": b["cpf"], "empresa": b["empresa"],
        "sensiveis": [], "motor": "local",
    }


# --------------------------------------------------------------- motor Claude
def _schema(nomes: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "tipo": {"type": "string", "enum": nomes + ["Não identificado"]},
            "inicia_documento": {"type": "boolean"},
            "confianca": {"type": "integer"},
            "alternativas": {"type": "array", "items": {"type": "string", "enum": nomes + ["Não identificado"]}},
            "pessoa": {"type": "string"},
            "cpf": {"type": "string"},
            "empresa": {"type": "string"},
            "sinais": {"type": "array", "items": {"type": "string"}},
            "dados_sensiveis": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "categoria": {"type": "string", "enum": ["cpf", "banco", "saude", "endereco", "contato"]},
                    "trecho": {"type": "string"},
                },
                "required": ["categoria", "trecho"], "additionalProperties": False}},
        },
        "required": ["tipo", "inicia_documento", "confianca", "alternativas", "pessoa", "cpf", "empresa",
                     "sinais", "dados_sensiveis"],
        "additionalProperties": False,
    }


def _imagem_b64(png: str) -> str:
    with Image.open(png) as im:
        im = im.convert("RGB")
        im.thumbnail((1568, 1568))
        buf = io.BytesIO()
        im.save(buf, "PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def analisar_claude(png: str, texto: str, tipos: list[dict], anterior: dict | None) -> dict:
    import anthropic

    nomes = [t["nome"] for t in tipos]
    ant = ("nenhuma: esta é a primeira página do envio" if not anterior else
           f"tipo “{anterior.get('tipo')}”, pessoa “{anterior.get('pessoa') or '-'}”, CPF “{anterior.get('cpf') or '-'}”")
    prompt = f"""Você analisa uma página de um lote de documentos digitalizados de gestão de terceiros (documentos trabalhistas de colaboradores terceirizados). O lote vem misturado: vários documentos em sequência, fora de ordem, às vezes fotografados.

Olhe a imagem e o texto lido pelo OCR (que pode ter erros) e decida:
1. tipo: qual destes tipos é esta página: {", ".join(nomes)}. Use "Não identificado" se nenhum servir.
2. inicia_documento: true se esta página começa um documento novo; false se continua o documento da página anterior. Use o visual (cabeçalho, logotipo, carimbos, assinaturas, layout), a numeração ("1 de 2") e mudanças de pessoa ou CPF.
3. confianca: de 0 a 100, calibrada. Fique abaixo de 75 sempre que houver dúvida real sobre o tipo ou sobre onde o documento começa.
4. alternativas: até 2 outros tipos plausíveis.
5. pessoa, cpf, empresa: como aparecem na página; texto vazio se não houver.
6. sinais: 1 a 3 frases curtas em português explicando o que você observou (ex.: "Imagem: carimbo diferente da página anterior").
7. dados_sensiveis: trechos copiados exatamente como estão no texto do OCR com CPF/RG, dados bancários, dados de saúde (CID, diagnóstico), endereço ou contato pessoal.

Página anterior: {ant}.

<texto_ocr>
{(texto or '')[:6000]}
</texto_ocr>"""
    cliente = anthropic.Anthropic()
    pedido = dict(
        model=config.MODELO,
        max_tokens=8000,
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": _schema(nomes)}},
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _imagem_b64(png)}},
            {"type": "text", "text": prompt},
        ]}],
    )
    try:
        resp = cliente.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **pedido)
    except TypeError:
        resp = cliente.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                            extra_body={"fallbacks": "default"}, **pedido)
    if resp.stop_reason == "refusal":
        raise RuntimeError("o modelo recusou a página")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("resposta cortada")
    dados = json.loads(next(b.text for b in resp.content if b.type == "text"))
    conf = int(max(0, min(100, dados["confianca"])))
    cands = [[dados["tipo"], conf]] + [[a, max(1, (100 - conf) // 2)] for a in dados["alternativas"][:2] if a != dados["tipo"]]
    return {
        "tipo": dados["tipo"], "conf": conf, "inicio": bool(dados["inicia_documento"]) or anterior is None,
        "sinais": ["Claude (imagem + texto): " + s for s in dados["sinais"][:3]],
        "candidatos": cands, "pessoa": dados["pessoa"] or None, "cpf": dados["cpf"] or None,
        "empresa": dados["empresa"] or None, "sensiveis": dados["dados_sensiveis"], "motor": "claude",
    }


def analisar(png, texto, tipos, anterior, exemplos, usar_claude: bool) -> dict:
    if usar_claude and config.claude_configurado():
        import anthropic
        try:
            return analisar_claude(png, texto, tipos, anterior)
        except anthropic.RateLimitError:
            aviso = "Claude ocupado (limite de uso); usada a leitura local"
        except anthropic.APIConnectionError:
            aviso = "Sem conexão com o Claude; usada a leitura local"
        except anthropic.APIStatusError as e:
            aviso = f"Claude respondeu erro {e.status_code}; usada a leitura local"
        except Exception as e:  # resposta inesperada ou recusa
            aviso = f"Claude não concluiu ({e}); usada a leitura local"
        r = analisar_local(texto, tipos, anterior, exemplos)
        r["sinais"].insert(0, aviso)
        return r
    return analisar_local(texto, tipos, anterior, exemplos)
