"""Helpers compartidos para scripts de diagnostico de base de datos."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bootstrap.settings import database_url_from_env
from project_env import load_project_env
from repositories.common.postgres import postgres_connection


def open_connection():
    """Abre una conexion PostgreSQL resolviendo el entorno del proyecto."""

    load_project_env()
    database_url = database_url_from_env()
    if not database_url:
        raise SystemExit(
            "No encontré ACADEMIC_AGENT_DATABASE_URL ni variables PGHOST/PGPORT/PGDATABASE/PGUSER."
        )
    return postgres_connection(database_url)


def print_section(title: str) -> None:
    """Imprime un encabezado simple de diagnostico."""

    print(f"\n== {title} ==")


def print_kv_rows(rows: list[dict[str, Any]]) -> None:
    """Imprime filas como pares clave=valor, una por bloque."""

    if not rows:
        print("(sin filas)")
        return

    for index, row in enumerate(rows, start=1):
        print(f"[fila {index}]")
        for key, value in row.items():
            print(f"  {key}: {value}")


def require_student_exists(conn: Any, *, student_id: int) -> dict[str, Any]:
    """Valida que el estudiante exista antes de correr los checks."""

    student = conn.execute(
        """
        SELECT id, full_name, student_code, institutional_email
        FROM students
        WHERE id = %s
        """,
        (student_id,),
    ).fetchone()
    if student is None:
        raise SystemExit(f"No existe students.id={student_id}.")
    return dict(student)

