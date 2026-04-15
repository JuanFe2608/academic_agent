"""Checkpointer PostgreSQL para persistir hilos e historial de LangGraph."""

from __future__ import annotations

import asyncio
import os
import random
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    WRITES_IDX_MAP,
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
    PendingWrite,
    get_checkpoint_id,
    get_checkpoint_metadata,
)
from psycopg import connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from bootstrap.settings import checkpoint_database_url_from_env as _checkpoint_database_url_from_env
from utils.message_sanitizer import sanitize_persisted_payload

_CHECKPOINTS_TABLE = "langgraph_thread_checkpoints"
_WRITES_TABLE = "langgraph_checkpoint_writes"
_REQUIRED_TABLES = (_CHECKPOINTS_TABLE, _WRITES_TABLE)


def checkpoint_database_url_from_env() -> str:
    """Resuelve la base de datos para la persistencia de hilos de LangGraph."""

    return _checkpoint_database_url_from_env()


class PostgresLangGraphCheckpointer(BaseCheckpointSaver[str]):
    """Implementación mínima y persistente de checkpoints sobre PostgreSQL."""

    def __init__(self, database_url: str) -> None:
        super().__init__()
        self.database_url = database_url

    def _connect(self):
        return connect(self.database_url, row_factory=dict_row)

    def _config_parts(self, config: RunnableConfig) -> tuple[str, str, str | None]:
        configurable = config.get("configurable", {})
        thread_id = str(configurable["thread_id"])
        checkpoint_ns = str(configurable.get("checkpoint_ns", ""))
        checkpoint_id = get_checkpoint_id(config)
        return thread_id, checkpoint_ns, checkpoint_id

    def _deserialize_checkpoint(self, row: dict[str, Any]) -> Checkpoint:
        return self.serde.loads_typed(
            (row["checkpoint_type"], bytes(row["checkpoint_payload"]))
        )

    def _load_pending_writes(
        self,
        thread_id: str,
        checkpoint_ns: str,
        checkpoint_id: str,
    ) -> list[PendingWrite]:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT task_id, channel, value_type, value_payload
                FROM {_WRITES_TABLE}
                WHERE thread_id = %s
                  AND checkpoint_ns = %s
                  AND checkpoint_id = %s
                ORDER BY task_id, write_idx
                """,
                (thread_id, checkpoint_ns, checkpoint_id),
            )
            rows = cur.fetchall()

        return [
            (
                str(row["task_id"]),
                str(row["channel"]),
                self.serde.loads_typed((row["value_type"], bytes(row["value_payload"]))),
            )
            for row in rows
        ]

    def _row_to_tuple(self, row: dict[str, Any]) -> CheckpointTuple:
        thread_id = str(row["thread_id"])
        checkpoint_ns = str(row["checkpoint_ns"])
        checkpoint_id = str(row["checkpoint_id"])
        parent_checkpoint_id = row["parent_checkpoint_id"]

        return CheckpointTuple(
            config={
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_ns": checkpoint_ns,
                    "checkpoint_id": checkpoint_id,
                }
            },
            checkpoint=self._deserialize_checkpoint(row),
            metadata=dict(row["metadata_json"] or {}),
            parent_config=(
                {
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": str(parent_checkpoint_id),
                    }
                }
                if parent_checkpoint_id
                else None
            ),
            pending_writes=self._load_pending_writes(
                thread_id,
                checkpoint_ns,
                checkpoint_id,
            ),
        )

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        thread_id, checkpoint_ns, checkpoint_id = self._config_parts(config)
        params: list[Any] = [thread_id, checkpoint_ns]
        query = f"""
            SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                   checkpoint_type, checkpoint_payload, metadata_json
            FROM {_CHECKPOINTS_TABLE}
            WHERE thread_id = %s
              AND checkpoint_ns = %s
        """
        if checkpoint_id:
            query += " AND checkpoint_id = %s"
            params.append(checkpoint_id)
        query += " ORDER BY checkpoint_id DESC LIMIT 1"

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, tuple(params))
            row = cur.fetchone()

        if row is None:
            return None
        return self._row_to_tuple(row)

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        params: list[Any] = []
        where: list[str] = []
        if config is not None:
            thread_id, checkpoint_ns, checkpoint_id = self._config_parts(config)
            where.extend(["thread_id = %s", "checkpoint_ns = %s"])
            params.extend([thread_id, checkpoint_ns])
            if checkpoint_id:
                where.append("checkpoint_id = %s")
                params.append(checkpoint_id)

        before_checkpoint_id = get_checkpoint_id(before) if before else None
        if before_checkpoint_id:
            where.append("checkpoint_id < %s")
            params.append(before_checkpoint_id)

        if filter:
            where.append("metadata_json @> %s")
            params.append(Jsonb(filter))

        query = f"""
            SELECT thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id,
                   checkpoint_type, checkpoint_payload, metadata_json
            FROM {_CHECKPOINTS_TABLE}
        """
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY checkpoint_id DESC"
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

        for row in rows:
            yield self._row_to_tuple(row)

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        del new_versions
        thread_id, checkpoint_ns, _ = self._config_parts(config)
        checkpoint_to_store = sanitize_persisted_payload(checkpoint.copy())
        checkpoint_to_store["id"] = str(checkpoint_to_store["id"])
        checkpoint_type, checkpoint_payload = self.serde.dumps_typed(checkpoint_to_store)
        metadata_json = get_checkpoint_metadata(config, metadata)

        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO {_CHECKPOINTS_TABLE} (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    parent_checkpoint_id,
                    checkpoint_type,
                    checkpoint_payload,
                    metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id) DO UPDATE
                SET parent_checkpoint_id = EXCLUDED.parent_checkpoint_id,
                    checkpoint_type = EXCLUDED.checkpoint_type,
                    checkpoint_payload = EXCLUDED.checkpoint_payload,
                    metadata_json = EXCLUDED.metadata_json
                """,
                (
                    thread_id,
                    checkpoint_ns,
                    str(checkpoint_to_store["id"]),
                    config.get("configurable", {}).get("checkpoint_id"),
                    checkpoint_type,
                    checkpoint_payload,
                    Jsonb(metadata_json),
                ),
            )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": str(checkpoint_to_store["id"]),
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        thread_id, checkpoint_ns, checkpoint_id = self._config_parts(config)
        if not checkpoint_id:
            raise ValueError("No se puede persistir pending writes sin checkpoint_id.")

        rows: list[tuple[Any, ...]] = []
        for idx, (channel, value) in enumerate(writes):
            value_type, value_payload = self.serde.dumps_typed(
                sanitize_persisted_payload(value)
            )
            rows.append(
                (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    task_id,
                    task_path,
                    WRITES_IDX_MAP.get(channel, idx),
                    channel,
                    value_type,
                    value_payload,
                )
            )

        if not rows:
            return

        with self._connect() as conn, conn.cursor() as cur:
            cur.executemany(
                f"""
                INSERT INTO {_WRITES_TABLE} (
                    thread_id,
                    checkpoint_ns,
                    checkpoint_id,
                    task_id,
                    task_path,
                    write_idx,
                    channel,
                    value_type,
                    value_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
                DO NOTHING
                """,
                rows,
            )

    def delete_thread(self, thread_id: str) -> None:
        with self._connect() as conn, conn.cursor() as cur:
            cur.execute(
                f"DELETE FROM {_WRITES_TABLE} WHERE thread_id = %s",
                (thread_id,),
            )
            cur.execute(
                f"DELETE FROM {_CHECKPOINTS_TABLE} WHERE thread_id = %s",
                (thread_id,),
            )

    async def aget_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        return await asyncio.to_thread(self.get_tuple, config)

    async def alist(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> AsyncIterator[CheckpointTuple]:
        tuples = await asyncio.to_thread(
            lambda: list(self.list(config, filter=filter, before=before, limit=limit))
        )
        for tuple_ in tuples:
            yield tuple_

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        return await asyncio.to_thread(
            self.put,
            config,
            checkpoint,
            metadata,
            new_versions,
        )

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[tuple[str, Any]],
        task_id: str,
        task_path: str = "",
    ) -> None:
        await asyncio.to_thread(self.put_writes, config, writes, task_id, task_path)

    async def adelete_thread(self, thread_id: str) -> None:
        await asyncio.to_thread(self.delete_thread, thread_id)

    async def aget_iter(self, config: RunnableConfig) -> AsyncIterator[CheckpointTuple]:
        tuple_ = await self.aget_tuple(config)
        if tuple_ is not None:
            yield tuple_

    def get_next_version(self, current: str | None, channel: None) -> str:
        del channel
        if current is None:
            current_v = 0
        elif isinstance(current, int):
            current_v = current
        else:
            current_v = int(str(current).split(".")[0])
        next_v = current_v + 1
        return f"{next_v:032}.{random.random():.16f}"


def _assert_schema_ready(database_url: str) -> None:
    with connect(database_url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name = ANY(%s)
            ORDER BY table_name
            """,
            (list(_REQUIRED_TABLES),),
        )
        found = {str(row["table_name"]) for row in cur.fetchall()}

    missing = [table for table in _REQUIRED_TABLES if table not in found]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            "Faltan tablas para la persistencia de hilos de LangGraph: "
            f"{missing_str}. Ejecuta la migracion "
            "'migrations/0003_langgraph_thread_persistence.sql' en PostgreSQL y reinicia 'langgraph dev'."
        )


def create_checkpointer() -> PostgresLangGraphCheckpointer:
    """Factory usada por `langgraph.json` para activar persistencia real de threads."""

    database_url = checkpoint_database_url_from_env()
    if not database_url:
        raise RuntimeError(
            "No se encontro una URL de PostgreSQL para el checkpointer de LangGraph. "
            "Configura `LANGGRAPH_CHECKPOINTER_DATABASE_URL` o usa "
            "`ACADEMIC_AGENT_DATABASE_URL` / `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` / `PGPASSWORD`."
        )

    _assert_schema_ready(database_url)
    return PostgresLangGraphCheckpointer(database_url)
