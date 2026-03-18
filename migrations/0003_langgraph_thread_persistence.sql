BEGIN;

CREATE TABLE IF NOT EXISTS langgraph_thread_checkpoints (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    parent_checkpoint_id TEXT NULL,
    checkpoint_type TEXT NOT NULL,
    checkpoint_payload BYTEA NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE IF NOT EXISTS langgraph_checkpoint_writes (
    id BIGSERIAL PRIMARY KEY,
    thread_id TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    task_path TEXT NOT NULL DEFAULT '',
    write_idx INTEGER NOT NULL,
    channel TEXT NOT NULL,
    value_type TEXT NOT NULL,
    value_payload BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx)
);

CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_thread_ns_checkpoint
    ON langgraph_thread_checkpoints (thread_id, checkpoint_ns, checkpoint_id DESC);

CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoints_created_at
    ON langgraph_thread_checkpoints (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_langgraph_checkpoint_writes_outer_key
    ON langgraph_checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id, task_id, write_idx);

COMMIT;
