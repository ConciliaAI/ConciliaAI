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
"""
with _lock:
    _con.executescript(SCHEMA)
    # Colunas novas em bancos criados por versões anteriores.
    for tabela, coluna in (("envios", "gabarito TEXT"), ("envios", "usuario TEXT"), ("docs", "decidido_por TEXT"),
                           ("acessos", "usuario TEXT")):
        try:
            _con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna}")
        except sqlite3.OperationalError:
            pass
    _con.commit()


def evento(envio_id, texto):
    x("INSERT INTO eventos(envio_id, quando, texto) VALUES(?,?,?)", (envio_id, agora(), texto))


def get_config(ws):
    padrao = {"cpf": "1", "banco": "1", "saude": "1", "endereco": "0", "contato": "1",
              "limiar": "75", "usar_claude": "1"}
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
