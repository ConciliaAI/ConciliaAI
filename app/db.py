"""Banco SQLite: workspaces (clientes), envios, páginas, documentos, busca e auditoria."""
import json
import sqlite3
import threading
from datetime import datetime

from .config import BANCO

_lock = threading.RLock()
_con = sqlite3.connect(BANCO, check_same_thread=False)
_con.row_factory = sqlite3.Row
_con.execute("PRAGMA journal_mode=WAL")
_con.execute("PRAGMA foreign_keys=ON")


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def q(sql, args=(), um=False):
    with _lock:
        cur = _con.execute(sql, args)
        linhas = [dict(r) for r in cur.fetchall()]
    return (linhas[0] if linhas else None) if um else linhas


def x(sql, args=()):
    with _lock:
        cur = _con.execute(sql, args)
        _con.commit()
        return cur.lastrowid


def inserir_se_novo(sql, args=()):
    """INSERT OR IGNORE com resposta baseada em rowcount, sem falso sucesso de lastrowid."""
    with _lock:
        cur = _con.execute(sql, args)
        _con.commit()
        return cur.rowcount == 1


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
CREATE VIRTUAL TABLE IF NOT EXISTS busca USING fts5(doc_id UNINDEXED, ws UNINDEXED, texto,
  tokenize="unicode61 remove_diacritics 2");
CREATE TABLE IF NOT EXISTS eventos(id INTEGER PRIMARY KEY, envio_id INT, quando TEXT, texto TEXT);
CREATE TABLE IF NOT EXISTS exemplos(id INTEGER PRIMARY KEY, ws TEXT, tipo TEXT, palavras TEXT);
CREATE TABLE IF NOT EXISTS acessos(id INTEGER PRIMARY KEY, ws TEXT, doc_id INT, quando TEXT, motivo TEXT, usuario TEXT);
CREATE TABLE IF NOT EXISTS arquivos(id INTEGER PRIMARY KEY, ws TEXT, sha256 TEXT, envio_id INT, nome TEXT);
CREATE TABLE IF NOT EXISTS usuarios(usuario TEXT PRIMARY KEY, nome TEXT, perfil TEXT, senha_hash TEXT);
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
  FOREIGN KEY(integracao_id) REFERENCES integracoes(id) ON DELETE SET NULL,
  FOREIGN KEY(ws) REFERENCES workspaces(id) ON DELETE RESTRICT
);
CREATE INDEX IF NOT EXISTS i_integracao_eventos_ws ON integracao_eventos(ws, quando);
CREATE TABLE IF NOT EXISTS documentos_fiscais (
  id INTEGER PRIMARY KEY, ws TEXT NOT NULL, envio_id INT NOT NULL,
  nome_arquivo TEXT, caminho_xml TEXT, sha256 TEXT NOT NULL,
  modelo TEXT NOT NULL, tipo TEXT NOT NULL, versao TEXT,
  numero TEXT, chave TEXT, emissao TEXT, emissor TEXT, destinatario TEXT,
  dados TEXT NOT NULL, criado_em TEXT NOT NULL,
  UNIQUE(ws, sha256));
CREATE INDEX IF NOT EXISTS i_fiscais_ws ON documentos_fiscais(ws, modelo, id);
"""
with _lock:
    _con.executescript(SCHEMA)
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
                           ("integracao_eventos", "ator_nome TEXT")):
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
