"""Arquivos da plataforma (imagens das páginas e originais enviados): disco local + Storage do Supabase.

O disco continua sendo onde o OCR trabalha. Com SUPABASE_URL e a chave secreta no .env, cada arquivo
também vai para um bucket privado do Storage (em segundo plano, sem atrasar a leitura do lote), e um
computador que não tem o arquivo o busca no Storage na primeira vez que precisar. Sem essa configuração,
tudo fica só no disco, como antes.

No banco os arquivos são guardados pela chave relativa à pasta de dados ("paginas/12_0001.png"), que vale
em qualquer computador. Caminhos absolutos antigos ("C:/.../dados/paginas/12_0001.png") também funcionam.
"""
import logging
import mimetypes
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

from . import config

log = logging.getLogger("concilia.arquivos")

PASTAS = ("paginas", "envios")  # o que vai para o Storage (miniaturas e PDFs são refeitos a partir das páginas)
LIMITE_BYTES = config.STORAGE_LIMITE_MB * 1024 * 1024
_fila = ThreadPoolExecutor(max_workers=2, thread_name_prefix="storage")
_bucket_pronto = threading.Event()
_pendentes = set()
_trava = threading.Lock()


def ativo() -> bool:
    return bool(config.SUPABASE_URL and config.SUPABASE_CHAVE)


def chave(caminho) -> str | None:
    """Chave relativa à pasta de dados, a partir de paginas/ ou envios/, com barras normais."""
    if not caminho:
        return None
    partes = str(caminho).replace("\\", "/").split("/")
    for i in range(len(partes) - 1, -1, -1):
        if partes[i] in PASTAS and i < len(partes) - 1:
            return "/".join(partes[i:])
    return None


def caminho_local(c) -> Path | None:
    k = chave(c)
    return config.DADOS / k if k else (Path(c) if c else None)


# ------------------------------------------------------------------ HTTP do Storage
def _cabecalhos(extra=None):
    h = {"apikey": config.SUPABASE_CHAVE}
    if not config.SUPABASE_CHAVE.startswith("sb_"):
        h["Authorization"] = f"Bearer {config.SUPABASE_CHAVE}"  # chave antiga (service_role, em JWT)
    return {**h, **(extra or {})}


def _requisicao(metodo, caminho, **kw):
    """Ponto único de rede (os testes trocam esta função por um Storage em memória)."""
    import httpx
    url = f"{config.SUPABASE_URL.rstrip('/')}/storage/v1/{caminho}"
    return httpx.request(metodo, url, headers=_cabecalhos(kw.pop("headers", None)), timeout=60, **kw)


def _objeto(k):
    return f"object/{config.STORAGE_BUCKET}/{quote(k)}"


def garantir_bucket():
    """Cria o bucket privado na primeira vez (idempotente)."""
    if not ativo() or _bucket_pronto.is_set():
        return
    r = _requisicao("GET", f"bucket/{config.STORAGE_BUCKET}")
    if r.status_code != 200:
        r = _requisicao("POST", "bucket", json={"id": config.STORAGE_BUCKET, "name": config.STORAGE_BUCKET,
                                                "public": False, "file_size_limit": LIMITE_BYTES})
        if r.status_code not in (200, 201) and "already exists" not in r.text.lower():
            raise RuntimeError(f"Não foi possível criar o bucket do Storage ({r.status_code}): {r.text[:200]}")
    _bucket_pronto.set()


def _subir(local: Path, k: str):
    try:
        garantir_bucket()
        tipo = mimetypes.guess_type(local.name)[0] or "application/octet-stream"
        r = _requisicao("POST", _objeto(k), content=local.read_bytes(),
                        headers={"Content-Type": tipo, "x-upsert": "true"})
        if r.status_code not in (200, 201):
            log.warning("Storage recusou %s (%s): %s", k, r.status_code, r.text[:200])
    except Exception as erro:  # sem rede: o arquivo continua no disco e a plataforma segue
        log.warning("Não foi possível enviar %s ao Storage: %s", k, erro)


def enviar(caminho, esperar=False):
    """Manda o arquivo para o Storage (em segundo plano). Arquivos acima do limite ficam só no disco."""
    k, local = chave(caminho), caminho_local(caminho)
    if not ativo() or not k or not local or not local.exists():
        return
    if local.stat().st_size > LIMITE_BYTES:
        log.info("%s passa de %s MB: fica só no disco.", k, config.STORAGE_LIMITE_MB)
        return
    tarefa = _fila.submit(_subir, local, k)
    with _trava:
        _pendentes.add(tarefa)
    tarefa.add_done_callback(lambda t: _pendentes.discard(t))
    if esperar:
        tarefa.result()


def local(caminho) -> Path | None:
    """Caminho no disco deste computador; se o arquivo não está aqui, busca no Storage."""
    destino = caminho_local(caminho)
    if not destino:
        return None
    if destino.exists():
        return destino
    k = chave(caminho)
    if not ativo() or not k:
        return None
    try:
        r = _requisicao("GET", _objeto(k))
    except Exception as erro:
        log.warning("Não foi possível buscar %s no Storage: %s", k, erro)
        return None
    if r.status_code != 200:
        return None
    destino.parent.mkdir(parents=True, exist_ok=True)
    temporario = destino.with_suffix(destino.suffix + ".parcial")
    temporario.write_bytes(r.content)
    temporario.replace(destino)
    return destino


def apagar(caminhos):
    """Apaga do disco e do Storage."""
    chaves = []
    for c in caminhos:
        destino = caminho_local(c)
        if destino:
            try:
                destino.unlink(missing_ok=True)
            except OSError:
                pass
        if chave(c):
            chaves.append(chave(c))
    if ativo() and chaves:
        try:
            _requisicao("DELETE", f"object/{config.STORAGE_BUCKET}", json={"prefixes": chaves})
        except Exception as erro:
            log.warning("Não foi possível apagar do Storage: %s", erro)


def aguardar():
    """Espera os envios em andamento (usado nos testes)."""
    with _trava:
        tarefas = list(_pendentes)
    for t in tarefas:
        t.result()
