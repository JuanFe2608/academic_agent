BEGIN;

CREATE TABLE IF NOT EXISTS microsoft_graph_connections (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL,
    microsoft_user_id TEXT NULL,
    user_principal_name TEXT NULL,
    email TEXT NULL,
    display_name TEXT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NULL,
    token_type TEXT NOT NULL DEFAULT 'Bearer',
    scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    expires_at TIMESTAMPTZ NULL,
    calendar_id TEXT NULL,
    todo_task_list_id TEXT NULL,
    auth_metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(tenant_id)) BETWEEN 1 AND 120),
    CHECK (char_length(trim(access_token)) BETWEEN 20 AND 10000),
    CHECK (refresh_token IS NULL OR char_length(trim(refresh_token)) BETWEEN 20 AND 10000),
    CHECK (token_type IN ('Bearer')),
    CHECK (calendar_id IS NULL OR char_length(trim(calendar_id)) BETWEEN 1 AND 200),
    CHECK (todo_task_list_id IS NULL OR char_length(trim(todo_task_list_id)) BETWEEN 1 AND 200),
    CHECK (microsoft_user_id IS NULL OR char_length(trim(microsoft_user_id)) BETWEEN 1 AND 200),
    CHECK (user_principal_name IS NULL OR char_length(trim(user_principal_name)) BETWEEN 3 AND 320),
    CHECK (email IS NULL OR char_length(trim(email)) BETWEEN 3 AND 320),
    CHECK (display_name IS NULL OR char_length(trim(display_name)) BETWEEN 1 AND 300),
    CHECK (jsonb_typeof(scopes_json) = 'array'),
    CHECK (jsonb_typeof(auth_metadata) = 'object'),
    UNIQUE (student_id),
    UNIQUE (id, student_id)
);

CREATE TABLE IF NOT EXISTS outlook_calendar_event_links (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    microsoft_graph_connection_id BIGINT NOT NULL,
    study_plan_event_instance_id BIGINT NULL,
    source_instance_key TEXT NOT NULL,
    calendar_id TEXT NOT NULL,
    external_event_id TEXT NOT NULL,
    external_change_key TEXT NULL,
    sync_status TEXT NOT NULL DEFAULT 'active',
    last_error TEXT NULL,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(source_instance_key)) BETWEEN 3 AND 160),
    CHECK (char_length(trim(calendar_id)) BETWEEN 1 AND 200),
    CHECK (char_length(trim(external_event_id)) BETWEEN 1 AND 200),
    CHECK (external_change_key IS NULL OR char_length(trim(external_change_key)) BETWEEN 1 AND 200),
    CHECK (sync_status IN ('active', 'deleted', 'error')),
    CHECK (last_error IS NULL OR char_length(trim(last_error)) BETWEEN 1 AND 1000),
    UNIQUE (student_id, source_instance_key),
    UNIQUE (student_id, calendar_id, external_event_id),
    UNIQUE (id, student_id),
    CONSTRAINT fk_outlook_calendar_event_links_connection_student
        FOREIGN KEY (microsoft_graph_connection_id, student_id)
        REFERENCES microsoft_graph_connections(id, student_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_outlook_calendar_event_links_instance_student
        FOREIGN KEY (study_plan_event_instance_id, student_id)
        REFERENCES study_plan_event_instances(id, student_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS microsoft_todo_task_links (
    id BIGSERIAL PRIMARY KEY,
    student_id BIGINT NOT NULL REFERENCES students(id) ON DELETE CASCADE,
    microsoft_graph_connection_id BIGINT NOT NULL,
    study_plan_event_instance_id BIGINT NULL,
    source_instance_key TEXT NOT NULL,
    task_list_id TEXT NOT NULL,
    external_task_id TEXT NOT NULL,
    sync_status TEXT NOT NULL DEFAULT 'active',
    last_error TEXT NULL,
    last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(source_instance_key)) BETWEEN 3 AND 160),
    CHECK (char_length(trim(task_list_id)) BETWEEN 1 AND 200),
    CHECK (char_length(trim(external_task_id)) BETWEEN 1 AND 200),
    CHECK (sync_status IN ('active', 'deleted', 'error')),
    CHECK (last_error IS NULL OR char_length(trim(last_error)) BETWEEN 1 AND 1000),
    UNIQUE (student_id, source_instance_key),
    UNIQUE (student_id, task_list_id, external_task_id),
    UNIQUE (id, student_id),
    CONSTRAINT fk_microsoft_todo_task_links_connection_student
        FOREIGN KEY (microsoft_graph_connection_id, student_id)
        REFERENCES microsoft_graph_connections(id, student_id)
        ON DELETE CASCADE,
    CONSTRAINT fk_microsoft_todo_task_links_instance_student
        FOREIGN KEY (study_plan_event_instance_id, student_id)
        REFERENCES study_plan_event_instances(id, student_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_microsoft_graph_connections_expires_at
    ON microsoft_graph_connections (expires_at);

CREATE INDEX IF NOT EXISTS idx_outlook_calendar_event_links_student_status
    ON outlook_calendar_event_links (student_id, sync_status);

CREATE INDEX IF NOT EXISTS idx_outlook_calendar_event_links_instance
    ON outlook_calendar_event_links (study_plan_event_instance_id);

CREATE INDEX IF NOT EXISTS idx_microsoft_todo_task_links_student_status
    ON microsoft_todo_task_links (student_id, sync_status);

CREATE INDEX IF NOT EXISTS idx_microsoft_todo_task_links_instance
    ON microsoft_todo_task_links (study_plan_event_instance_id);

DROP TRIGGER IF EXISTS trg_microsoft_graph_connections_updated_at ON microsoft_graph_connections;
CREATE TRIGGER trg_microsoft_graph_connections_updated_at
BEFORE UPDATE ON microsoft_graph_connections
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_outlook_calendar_event_links_updated_at ON outlook_calendar_event_links;
CREATE TRIGGER trg_outlook_calendar_event_links_updated_at
BEFORE UPDATE ON outlook_calendar_event_links
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_microsoft_todo_task_links_updated_at ON microsoft_todo_task_links;
CREATE TRIGGER trg_microsoft_todo_task_links_updated_at
BEFORE UPDATE ON microsoft_todo_task_links
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

COMMIT;
