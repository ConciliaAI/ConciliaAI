"""Testa a migração de auditoria em um banco legado isolado."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path


def test_migracao_adiciona_identificacao_do_ator_sem_perder_historico(tmp_path):
    """A inicialização real de app.db deve migrar um SQLite antigo em diretório temporário."""
    banco = tmp_path / "concilia.db"

    # Simula a tabela existente antes da inclusão dos campos de identificação do ator.
    with sqlite3.connect(banco) as con:
        con.execute(
            """
            CREATE TABLE integracao_eventos (
                id INTEGER PRIMARY KEY,
                integracao_id INTEGER,
                ws TEXT NOT NULL,
                acao TEXT NOT NULL,
                endpoint TEXT,
                status INTEGER,
                quando TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            INSERT INTO integracao_eventos
                (id, integracao_id, ws, acao, endpoint, status, quando)
            VALUES (41, NULL, 'workspace-legado', 'criacao', '/api/integracoes', 200,
                    '2026-01-15 10:30:00')
            """
        )

    # Importar app.db em um processo novo é essencial: a conexão global do módulo
    # precisa nascer apontando para o banco temporário, e não para o banco dos testes.
    raiz_projeto = Path(__file__).resolve().parents[1]
    ambiente = os.environ.copy()
    ambiente["CONCILIA_DADOS"] = str(tmp_path)
    ambiente["PYTHONPATH"] = str(raiz_projeto) + os.pathsep + ambiente.get("PYTHONPATH", "")

    processo = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app import db; "
            "assert db._con.execute('PRAGMA database_list').fetchone()[2].endswith('concilia.db')",
        ],
        cwd=raiz_projeto,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )
    assert processo.returncode == 0, (
        "A inicialização/migração de app.db falhou no banco temporário. "
        f"stdout: {processo.stdout}\nstderr: {processo.stderr}"
    )

    # A conexão do processo filho foi encerrada; agora verificamos o resultado.
    with sqlite3.connect(banco) as con:
        colunas = {
            linha[1]
            for linha in con.execute("PRAGMA table_info(integracao_eventos)").fetchall()
        }
        assert {"ator_usuario", "ator_nome", "ator_perfil"} <= colunas

        evento = con.execute(
            """
            SELECT id, ws, acao, endpoint, status, quando,
                   ator_usuario, ator_nome, ator_perfil
            FROM integracao_eventos
            WHERE id = 41
            """
        ).fetchone()
        assert evento == (
            41,
            "workspace-legado",
            "criacao",
            "/api/integracoes",
            200,
            "2026-01-15 10:30:00",
            None,
            None,
            None,
        )

        # A migração também deve instalar os bloqueios de imutabilidade.
        try:
            con.execute("UPDATE integracao_eventos SET acao = 'alterada' WHERE id = 41")
            raise AssertionError("A migração não bloqueou UPDATE no histórico de auditoria.")
        except sqlite3.IntegrityError:
            con.rollback()

        try:
            con.execute("DELETE FROM integracao_eventos WHERE id = 41")
            raise AssertionError("A migração não bloqueou DELETE no histórico de auditoria.")
        except sqlite3.IntegrityError:
            con.rollback()

        preservado = con.execute(
            "SELECT acao FROM integracao_eventos WHERE id = 41"
        ).fetchone()
        assert preservado == ("criacao",)
