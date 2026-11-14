"""Banco: workspaces (clientes), envios, páginas, documentos, busca e auditoria.

Dois motores com o mesmo código:
- SQLite (padrão): arquivo dados/concilia.db, sem instalar nada.
- Postgres (ex.: Supabase): quando DATABASE_URL está no .env. O SQL do sistema é escrito no dialeto
  do SQLite (placeholders ?, INSERT OR IGNORE...) e traduzido aqui; o esquema também.
"""
import json
import re
import sqlite3
import threading
from datetime import datetime
from functools import lru_cache

from .config import BANCO, BANCO_URL, PG_ESQUEMA

POSTGRES = BANCO_URL.startswith(("postgres://", "postgresql://"))
_lock = threading.RLock()

# Tabelas com id numérico gerado pelo banco: no Postgres o INSERT devolve o id com RETURNING.
_COM_ID = {"tipos", "envios", "paginas", "docs", "eventos", "exemplos", "acessos", "arquivos", "fornecedores",
           "contratos", "aditivos", "notas", "divergencias", "trilha", "avisos", "integracoes", "integracao_eventos",
           "integracao_requisicoes", "documentos_fiscais"}


@lru_cache(maxsize=2048)
def _para_postgres(sql: str) -> str:
    """Traduz o SQL do sistema (dialeto SQLite) para o Postgres."""
    saida, dentro = [], False
    for ch in sql:
        if ch == "'":
            dentro = not dentro
            saida.append(ch)
        elif ch == "%":
            saida.append("%%")  # o psycopg trata % como início de parâmetro, inclusive dentro de texto
        elif ch == "?" and not dentro:
            saida.append("%s")
        else:
            saida.append(ch)
    sql = "".join(saida)
    ignorar = re.match(r"\s*INSERT\s+OR\s+IGNORE\s+INTO", sql, re.I)
    if ignorar:
        sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, count=1, flags=re.I).rstrip().rstrip(";")
        sql += " ON CONFLICT DO NOTHING"
    insert = re.match(r"\s*INSERT\s+INTO\s+(\w+)", sql, re.I)
    if insert and insert.group(1).lower() in _COM_ID and not re.search(r"\bRETURNING\b", sql, re.I):
        sql = sql.rstrip().rstrip(";") + " RETURNING id"
    return sql


class Linha(dict):
    """Linha do resultado: acessa por nome (r["id"]) e por posição (r[0]), como o sqlite3.Row."""

    def __getitem__(self, chave):
        if isinstance(chave, int):
            return list(self.values())[chave]
        return super().__getitem__(chave)


class _Cursor:
    def __init__(self, cur, lastrowid):
        self._cur, self.lastrowid, self.rowcount = cur, lastrowid, cur.rowcount

    def fetchone(self):
        return self._cur.fetchone() if self._cur.description else None

    def fetchall(self):
        return self._cur.fetchall() if self._cur.description else []


def normalizar_url(url: str) -> str:
    """Aceita a senha como foi digitada, mesmo com @ # / ? : (o Postgres exige esses símbolos codificados).

    O usuário é o que vem antes do primeiro ":" e o servidor é o que vem depois do último "@".
    Senhas já codificadas (com %40, %23...) passam do jeito que estão.
    """
    from urllib.parse import quote
    m = re.match(r"^(postgres(?:ql)?://)([^:/@]+):(.*)@([^@]+)$", url)
    if not m or re.search(r"%[0-9A-Fa-f]{2}", m.group(3)):
        return url
    return f"{m.group(1)}{m.group(2)}:{quote(m.group(3), safe='')}@{m.group(4)}"


class _ConexaoPostgres:
    """Expõe execute(sql, args) com a mesma cara da conexão do SQLite (lastrowid, rowcount, fetchone)."""

    def __init__(self, url):
        import psycopg
        from psycopg.types.numeric import FloatLoader

        def fabrica(cursor):
            nomes = [c.name for c in cursor.description or []]
            return lambda valores: Linha(zip(nomes, valores))

        self._psycopg = psycopg
        # prepare_threshold=None: funciona também pelo pooler do Supabase (porta 6543), que não guarda
        # comandos preparados entre conexões.
        self._con = psycopg.connect(normalizar_url(url), autocommit=True, row_factory=fabrica, prepare_threshold=None)
        self._con.adapters.register_loader("numeric", FloatLoader)  # SUM/AVG voltam float, como no SQLite
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", PG_ESQUEMA):
            raise ValueError("CONCILIA_PG_ESQUEMA inválido: use letras minúsculas, números e _.")
        self._con.execute(f"CREATE SCHEMA IF NOT EXISTS {PG_ESQUEMA}")
        self._con.execute(f"SET search_path TO {PG_ESQUEMA}, public, extensions")
        self._transacoes = 0

    @property
    def in_transaction(self):
        return self._transacoes > 0

    def execute(self, sql, args=()):
        cur = self._con.execute(_para_postgres(sql), tuple(args) or None)
        lastrowid = None
        if cur.description and len(cur.description) == 1 and cur.description[0].name == "id" \
                and re.match(r"\s*INSERT", sql, re.I):
            linha = cur.fetchone()
            lastrowid = linha["id"] if linha else None
        return _Cursor(cur, lastrowid)

    def executescript(self, script):
        self._con.execute(script)

    def transaction(self):
        return self._con.transaction()

    def commit(self):
        pass  # autocommit fora de db.transacao


def _conectar():
    if POSTGRES:
        return _ConexaoPostgres(BANCO_URL)
    con = sqlite3.connect(BANCO, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con


_con = _conectar()


def _executar(sql, args):
    """Executa um comando; no Postgres, refaz a conexão uma vez se ela caiu (ex.: inatividade no Supabase)."""
    global _con
    try:
        return _con.execute(sql, args)
    except Exception as erro:
        if POSTGRES and isinstance(erro, _con._psycopg.OperationalError) and not _con.in_transaction:
            _con = _conectar()
            return _con.execute(sql, args)
        raise


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def q(sql, args=(), um=False):
    with _lock:
        cur = _executar(sql, args)
        linhas = [dict(r) for r in cur.fetchall()]
    return (linhas[0] if linhas else None) if um else linhas


def x(sql, args=()):
    with _lock:
        cur = _executar(sql, args)
        _con.commit()
        return cur.lastrowid


def transacao(operacao):
    """Executa uma unidade atômica, inclusive quando chamada dentro de outra transação.

    SQLite: BEGIN IMMEDIATE no nível externo e SAVEPOINT nas chamadas aninhadas.
    Postgres: transaction() do psycopg, que também vira SAVEPOINT quando aninhada.
    """
    with _lock:
        if POSTGRES:
            _con._transacoes += 1
            try:
                with _con.transaction():
                    return operacao(_con)
            finally:
                _con._transacoes -= 1
        aninhada = _con.in_transaction
        ponto = "db_transacao_aninhada"
        try:
            if aninhada:
                _con.execute(f"SAVEPOINT {ponto}")
            else:
                _con.execute("BEGIN IMMEDIATE")
            resultado = operacao(_con)
            if aninhada:
                _con.execute(f"RELEASE SAVEPOINT {ponto}")
            else:
                _con.commit()
            return resultado
        except BaseException:
            if aninhada:
                _con.execute(f"ROLLBACK TO SAVEPOINT {ponto}")
                _con.execute(f"RELEASE SAVEPOINT {ponto}")
            else:
                _con.rollback()
            raise


def inserir_se_novo(sql, args=()):
    """INSERT OR IGNORE com resposta baseada em rowcount, sem falso sucesso de lastrowid."""
    with _lock:
        cur = _executar(sql, args)
        _con.commit()
        return cur.rowcount == 1


def buscar_texto(ws, termos, limite=30):
    """Documentos do workspace cujo texto tem todas as palavras (cada uma como começo de palavra).

    Devolve [{doc_id, trecho}] do mais relevante para o menos. termos já vêm sem acento e em minúsculas.
    """
    if POSTGRES:
        consulta = " & ".join(f"{t}:*" for t in termos)
        return q("""SELECT doc_id, ts_headline('simple', texto, to_tsquery('simple', ?),
                           'StartSel="",StopSel="",MaxWords=24,MinWords=8,MaxFragments=2,FragmentDelimiter=" … "') trecho
                    FROM busca WHERE ws=? AND tsv @@ to_tsquery('simple', ?)
                    ORDER BY ts_rank(tsv, to_tsquery('simple', ?)) DESC LIMIT ?""",
                 (consulta, ws, consulta, consulta, limite))
    consulta = " AND ".join(f'"{t}"*' for t in termos)
    return q("""SELECT doc_id, snippet(busca, 2, '', '', ' … ', 24) trecho FROM busca
                WHERE busca MATCH ? AND ws=? ORDER BY rank LIMIT ?""", (consulta, ws, limite))


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces(
  id TEXT PRIMARY KEY, nome TEXT, setor TEXT, cor TEXT, sigla TEXT, ordem INT);
CREATE TABLE IF NOT EXISTS tipos(
  id INTEGER PRIMARY KEY, ws TEXT, nome TEXT, titulos TEXT, palavras TEXT, exigido INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS config(ws TEXT, chave TEXT, valor TEXT, PRIMARY KEY(ws, chave));
CREATE TABLE IF NOT EXISTS envios(
  id INTEGER PRIMARY KEY, ws TEXT, nome TEXT, origem TEXT, criado_em TEXT,
  status TEXT, total INT DEFAULT 0, feitas INT DEFAULT 0, erro TEXT,
  retomadas INT DEFAULT 0, motor TEXT, falha_simulada INT DEFAULT 0, terminado_em TEXT);
CREATE TABLE IF NOT EXISTS paginas(
  id INTEGER PRIMARY KEY, envio_id INT, n INT, arquivo TEXT, indice INT, origem_tipo TEXT,
  status TEXT DEFAULT 'pendente', img TEXT, largura INT, altura INT,
  texto TEXT, linhas TEXT, fonte_texto TEXT,
  tipo TEXT, conf INT, inicio INT, sinais TEXT, candidatos TEXT,
  pessoa TEXT, cpf TEXT, empresa TEXT, sensiveis TEXT, motor TEXT, doc_id INT);
CREATE TABLE IF NOT EXISTS docs(
  id INTEGER PRIMARY KEY, envio_id INT, ws TEXT, tipo TEXT, conf INT, pag_ini INT, pag_fim INT,
  pessoa TEXT, cpf TEXT, empresa TEXT, status TEXT, duvida TEXT, motivo TEXT, sinais TEXT,
  candidatos TEXT, sensiveis TEXT, criado_em TEXT, decidido_em TEXT, decisao TEXT);
CREATE TABLE IF NOT EXISTS eventos(id INTEGER PRIMARY KEY, envio_id INT, quando TEXT, texto TEXT);
CREATE TABLE IF NOT EXISTS exemplos(id INTEGER PRIMARY KEY, ws TEXT, tipo TEXT, palavras TEXT);
CREATE TABLE IF NOT EXISTS acessos(id INTEGER PRIMARY KEY, ws TEXT, doc_id INT, quando TEXT, motivo TEXT, usuario TEXT);
CREATE TABLE IF NOT EXISTS arquivos(id INTEGER PRIMARY KEY, ws TEXT, sha256 TEXT, envio_id INT, nome TEXT);
CREATE TABLE IF NOT EXISTS usuarios(usuario TEXT PRIMARY KEY, nome TEXT, perfil TEXT, senha_hash TEXT);
-- Conta = a empresa que usa o sistema (escritório de BPO, contabilidade...). Os usuários e os workspaces
-- (os clientes dessa empresa) pertencem a uma conta, e ninguém enxerga os workspaces de outra conta.
CREATE TABLE IF NOT EXISTS contas(id TEXT PRIMARY KEY, nome TEXT NOT NULL, criado_em TEXT);
CREATE TABLE IF NOT EXISTS sessoes_encerradas(sid TEXT PRIMARY KEY, exp REAL);
-- Conciliação: a nota fiscal é o centro; contratos e aditivos são a referência.
CREATE TABLE IF NOT EXISTS fornecedores(
  id INTEGER PRIMARY KEY, ws TEXT, cnpj TEXT, nome TEXT, criado_em TEXT, UNIQUE(ws, cnpj));
CREATE TABLE IF NOT EXISTS contratos(
  id INTEGER PRIMARY KEY, ws TEXT, fornecedor_id INT, doc_id INT, envio_id INT, numero TEXT,
  cnpj_prestador TEXT, nome_prestador TEXT, cnpj_tomador TEXT, objeto TEXT, valor_mensal REAL, valor_total REAL,
  vigencia_inicio TEXT, vigencia_fim TEXT, criado_em TEXT);
CREATE TABLE IF NOT EXISTS aditivos(
  id INTEGER PRIMARY KEY, ws TEXT, doc_id INT, envio_id INT, numero TEXT, contrato_ref TEXT, cnpj_prestador TEXT,
  valor_adicional REAL, vigencia_inicio TEXT, vigencia_fim TEXT, criado_em TEXT);
CREATE TABLE IF NOT EXISTS notas(
  id INTEGER PRIMARY KEY, ws TEXT, fornecedor_id INT, contrato_id INT, doc_id INT, envio_id INT,
  origem TEXT, formato TEXT, chave TEXT, numero TEXT, data_emissao TEXT, competencia TEXT,
  cnpj_prestador TEXT, nome_prestador TEXT, cnpj_tomador TEXT, descricao TEXT, codigo_servico TEXT,
  valor REAL, valor_liquido REAL, contrato_ref TEXT, status TEXT, observacao TEXT, xml TEXT, criado_em TEXT);
CREATE TABLE IF NOT EXISTS divergencias(
  id INTEGER PRIMARY KEY, ws TEXT, nota_id INT, contrato_id INT, fornecedor_id INT, regra TEXT, severidade TEXT,
  mensagem TEXT, esperado TEXT, encontrado TEXT, status TEXT, decidido_por TEXT, decidido_em TEXT,
  comentario TEXT, criado_em TEXT);
CREATE TABLE IF NOT EXISTS trilha(id INTEGER PRIMARY KEY, ws TEXT, quando TEXT, usuario TEXT, texto TEXT);
CREATE TABLE IF NOT EXISTS avisos(
  id INTEGER PRIMARY KEY, ws TEXT, divergencia_id INT, nota_id INT, fornecedor_id INT, para TEXT,
  assunto TEXT, corpo TEXT, usuario TEXT, quando TEXT);
CREATE INDEX IF NOT EXISTS i_notas ON notas(ws, cnpj_prestador, numero);
CREATE INDEX IF NOT EXISTS i_div ON divergencias(ws, status);
-- Integrações ERP: credenciais técnicas isoladas por workspace.
CREATE TABLE IF NOT EXISTS integracoes(
  id INTEGER PRIMARY KEY,
  nome TEXT NOT NULL,
  ws TEXT NOT NULL,
  token_hash TEXT NOT NULL UNIQUE,
  token_prefix TEXT NOT NULL,
  permissoes TEXT NOT NULL DEFAULT '[]',
  ativa INTEGER NOT NULL DEFAULT 1,
  criada_em TEXT NOT NULL,
  expira_em TEXT,
  revogada_em TEXT,
  ultimo_acesso TEXT,
  FOREIGN KEY(ws) REFERENCES workspaces(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS i_integracoes_ws ON integracoes(ws, ativa);
CREATE TABLE IF NOT EXISTS integracao_eventos(
  id INTEGER PRIMARY KEY,
  integracao_id INTEGER,
  ws TEXT NOT NULL,
  acao TEXT NOT NULL,
  endpoint TEXT,
  status INTEGER,
  quando TEXT NOT NULL,
  ator_usuario TEXT,
  ator_nome TEXT,
  ator_perfil TEXT,
  FOREIGN KEY(integracao_id) REFERENCES integracoes(id) ON DELETE SET NULL,
  FOREIGN KEY(ws) REFERENCES workspaces(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS i_integracao_eventos_ws ON integracao_eventos(ws, quando);
-- Idempotência de requisições ERP; CREATE IF NOT EXISTS preserva bancos existentes.
CREATE TABLE IF NOT EXISTS integracao_requisicoes(
  id INTEGER PRIMARY KEY,
  integracao_id INTEGER NOT NULL,
  chave TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  tentativa_id TEXT,
  status TEXT NOT NULL DEFAULT 'processando'
    CHECK(status IN ('processando','indeterminado','concluido')),
  envio_id INTEGER,
  resposta_status INTEGER,
  resposta_json TEXT,
  criada_em TEXT NOT NULL,
  atualizada_em TEXT NOT NULL,
  UNIQUE(integracao_id, chave),
  FOREIGN KEY(integracao_id) REFERENCES integracoes(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS i_integracao_requisicoes_status
  ON integracao_requisicoes(integracao_id, status);
CREATE TABLE IF NOT EXISTS documentos_fiscais (
  id INTEGER PRIMARY KEY, ws TEXT NOT NULL, envio_id INT NOT NULL,
  nome_arquivo TEXT, caminho_xml TEXT, sha256 TEXT NOT NULL,
  modelo TEXT NOT NULL, tipo TEXT NOT NULL, versao TEXT,
  numero TEXT, chave TEXT, emissao TEXT, emissor TEXT, destinatario TEXT,
  dados TEXT NOT NULL, criado_em TEXT NOT NULL,
  UNIQUE(ws, sha256));
CREATE INDEX IF NOT EXISTS i_fiscais_ws ON documentos_fiscais(ws, modelo, id);
"""
# Partes que só existem no SQLite: busca de texto (FTS5) e auditoria imutável.
SCHEMA_SQLITE = """
CREATE VIRTUAL TABLE IF NOT EXISTS busca USING fts5(doc_id UNINDEXED, ws UNINDEXED, texto,
  tokenize="unicode61 remove_diacritics 2");
-- Eventos são append-only: nem a aplicação nem rotas administrativas podem
-- editar ou apagar registros existentes.
CREATE TRIGGER IF NOT EXISTS trg_integracao_eventos_sem_update
BEFORE UPDATE ON integracao_eventos
BEGIN
  SELECT RAISE(ABORT, 'Historico de auditoria e imutavel');
END;
CREATE TRIGGER IF NOT EXISTS trg_integracao_eventos_sem_delete
BEFORE DELETE ON integracao_eventos
BEGIN
  SELECT RAISE(ABORT, 'Historico de auditoria e imutavel');
END;
"""

# As mesmas partes no Postgres. A busca guarda o texto sem acento num tsvector (trigger), e a auditoria
# do ERP continua sem UPDATE nem DELETE.
SCHEMA_POSTGRES = """
CREATE TABLE IF NOT EXISTS busca(doc_id BIGINT, ws TEXT, texto TEXT, tsv TSVECTOR);
CREATE INDEX IF NOT EXISTS i_busca_tsv ON busca USING GIN(tsv);
CREATE INDEX IF NOT EXISTS i_busca_doc ON busca(doc_id);
CREATE OR REPLACE FUNCTION concilia_busca_tsv() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  -- Pontuação vira espaço, como no FTS5 do SQLite: "321.654.987-00" vira 321, 654, 987 e 00.
  NEW.tsv := to_tsvector('simple', regexp_replace({UNACCENT}(lower(coalesce(NEW.texto, ''))), '[^[:alnum:]]+', ' ', 'g'));
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_busca_tsv ON busca;
CREATE TRIGGER trg_busca_tsv BEFORE INSERT OR UPDATE OF texto ON busca
  FOR EACH ROW EXECUTE FUNCTION concilia_busca_tsv();
CREATE OR REPLACE FUNCTION concilia_auditoria_imutavel() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Historico de auditoria e imutavel';
END $$;
DROP TRIGGER IF EXISTS trg_integracao_eventos_sem_update ON integracao_eventos;
CREATE TRIGGER trg_integracao_eventos_sem_update BEFORE UPDATE ON integracao_eventos
  FOR EACH ROW EXECUTE FUNCTION concilia_auditoria_imutavel();
DROP TRIGGER IF EXISTS trg_integracao_eventos_sem_delete ON integracao_eventos;
CREATE TRIGGER trg_integracao_eventos_sem_delete BEFORE DELETE ON integracao_eventos
  FOR EACH ROW EXECUTE FUNCTION concilia_auditoria_imutavel();
"""


def _esquema_postgres(sql: str) -> str:
    """O esquema do SQLite no dialeto do Postgres (ids gerados, números com ponto flutuante)."""
    sql = re.sub(r"\bid INTEGER PRIMARY KEY\b", "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY", sql)
    return re.sub(r"\bREAL\b", "DOUBLE PRECISION", sql)


def _unaccent() -> str:
    """Função que tira acentos (extensão unaccent do Postgres; no Supabase fica no esquema extensions)."""
    try:
        _con.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    except Exception:
        pass  # sem permissão para criar extensão: usa a que já existir
    r = _con.execute("""SELECT n.nspname esquema FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace
                        WHERE e.extname='unaccent'""").fetchone()
    return f'{r["esquema"]}.unaccent' if r else ""


with _lock:
    if POSTGRES:
        _con.executescript(_esquema_postgres(SCHEMA))
        _con.executescript(SCHEMA_POSTGRES.replace("{UNACCENT}", _unaccent()))
    else:
        _con.executescript(SCHEMA)
        _con.executescript(SCHEMA_SQLITE)
    # Colunas novas em bancos criados por versões anteriores.
    for tabela, coluna in (("envios", "gabarito TEXT"), ("envios", "usuario TEXT"), ("docs", "decidido_por TEXT"),
                           ("acessos", "usuario TEXT"), ("docs", "dados TEXT"), ("docs", "aviso TEXT"),
                           ("envios", "notas_xml INT DEFAULT 0"), ("workspaces", "cnpj TEXT"),
                           ("fornecedores", "email TEXT"), ("fornecedores", "telefone TEXT"),
                           ("fornecedores", "responsavel TEXT"), ("fornecedores", "cadastro TEXT DEFAULT 'documento'"),
                           ("docs", "subtipo TEXT"), ("docs", "subtipo_pontos INTEGER"),
                           ("docs", "subtipo_evidencias TEXT"), ("docs", "subtipo_alternativas TEXT"),
                           ("docs", "subtipo_revisao INTEGER DEFAULT 1"),
                           ("docs", "subtipo_manual INTEGER DEFAULT 0"),
                           ("integracao_eventos", "ator_usuario TEXT"),
                           ("integracao_eventos", "ator_nome TEXT"),
                           ("integracao_eventos", "ator_perfil TEXT"),
                           ("integracao_requisicoes", "tentativa_id TEXT"),
                           ("usuarios", "conta_id TEXT"), ("workspaces", "conta_id TEXT")):
        if POSTGRES:
            _con.execute(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {_esquema_postgres(coluna)}")
            continue
        try:
            _con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna}")
        except sqlite3.OperationalError:
            pass
    _con.commit()


def evento(envio_id, texto):
    x("INSERT INTO eventos(envio_id, quando, texto) VALUES(?,?,?)", (envio_id, agora(), texto))


def trilha(ws, usuario, texto):
    """Registro permanente de decisões humanas (aprovar, rejeitar, reabrir)."""
    x("INSERT INTO trilha(ws, quando, usuario, texto) VALUES(?,?,?,?)", (ws, agora(), usuario, texto))


def get_config(ws):
    padrao = {"cpf": "1", "banco": "1", "saude": "1", "endereco": "0", "contato": "1",
              "limiar": "75", "usar_claude": "1", "tolerancia": "0"}
    for r in q("SELECT chave, valor FROM config WHERE ws=?", (ws,)):
        padrao[r["chave"]] = r["valor"]
    return padrao


def set_config(ws, chave, valor):
    x("INSERT INTO config(ws, chave, valor) VALUES(?,?,?) ON CONFLICT(ws, chave) DO UPDATE SET valor=excluded.valor",
      (ws, chave, str(valor)))


def tipos_ws(ws):
    out = []
    for r in q("SELECT * FROM tipos WHERE ws=? ORDER BY id", (ws,)):
        r["titulos"] = json.loads(r["titulos"] or "[]")
        r["palavras"] = json.loads(r["palavras"] or "[]")
        out.append(r)
    return out
