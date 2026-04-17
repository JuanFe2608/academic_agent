BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_extension
        WHERE extname = 'vector'
    ) THEN
        RAISE EXCEPTION
            'pgvector extension is required before applying 0016_rag_study_recommendations.sql. Ask a database administrator to run: CREATE EXTENSION IF NOT EXISTS vector;';
    END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS rag;

CREATE TABLE IF NOT EXISTS rag.ingestion_runs (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE,
    corpus_name TEXT NOT NULL,
    corpus_version TEXT NOT NULL,
    source_root TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'started',
    documents_count INTEGER NOT NULL DEFAULT 0,
    chunks_count INTEGER NOT NULL DEFAULT 0,
    relations_count INTEGER NOT NULL DEFAULT 0,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ NULL,
    CHECK (char_length(trim(run_id)) BETWEEN 8 AND 160),
    CHECK (char_length(trim(corpus_name)) BETWEEN 2 AND 120),
    CHECK (char_length(trim(corpus_version)) BETWEEN 1 AND 120),
    CHECK (char_length(trim(source_root)) BETWEEN 1 AND 500),
    CHECK (status IN ('started', 'completed', 'failed')),
    CHECK (documents_count >= 0),
    CHECK (chunks_count >= 0),
    CHECK (relations_count >= 0),
    CHECK (jsonb_typeof(metadata_json) = 'object'),
    CHECK (
        (status = 'completed' AND finished_at IS NOT NULL)
        OR status <> 'completed'
    )
);

CREATE TABLE IF NOT EXISTS rag.documents (
    id BIGSERIAL PRIMARY KEY,
    document_id TEXT NOT NULL UNIQUE,
    knowledge_type TEXT NOT NULL,
    document_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    name TEXT NOT NULL,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL,
    version TEXT NOT NULL,
    source_path TEXT NOT NULL,
    checksum TEXT NOT NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingestion_run_id BIGINT NULL REFERENCES rag.ingestion_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(document_id)) BETWEEN 3 AND 180),
    CHECK (char_length(trim(knowledge_type)) BETWEEN 3 AND 80),
    CHECK (char_length(trim(document_type)) BETWEEN 3 AND 120),
    CHECK (char_length(trim(entity_id)) BETWEEN 2 AND 160),
    CHECK (char_length(trim(name)) BETWEEN 2 AND 240),
    CHECK (jsonb_typeof(aliases) = 'array'),
    CHECK (char_length(trim(status)) BETWEEN 2 AND 80),
    CHECK (char_length(trim(version)) BETWEEN 1 AND 80),
    CHECK (char_length(trim(source_path)) BETWEEN 1 AND 500),
    CHECK (checksum ~ '^[a-f0-9]{64}$'),
    CHECK (jsonb_typeof(metadata_json) = 'object')
);

CREATE TABLE IF NOT EXISTS rag.chunks (
    id BIGSERIAL PRIMARY KEY,
    chunk_id TEXT NOT NULL UNIQUE,
    document_id TEXT NOT NULL REFERENCES rag.documents(document_id) ON DELETE CASCADE,
    knowledge_type TEXT NOT NULL,
    document_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    section_title TEXT NOT NULL,
    heading_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    chunk_kind TEXT NOT NULL,
    content TEXT NOT NULL,
    content_tsv TSVECTOR GENERATED ALWAYS AS (to_tsvector('spanish', content)) STORED,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding VECTOR(1536) NULL,
    position_in_document INTEGER NOT NULL,
    token_estimate INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    ingestion_run_id BIGINT NULL REFERENCES rag.ingestion_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(chunk_id)) BETWEEN 3 AND 260),
    CHECK (char_length(trim(document_id)) BETWEEN 3 AND 180),
    CHECK (char_length(trim(section_title)) BETWEEN 1 AND 240),
    CHECK (jsonb_typeof(heading_path) = 'array'),
    CHECK (char_length(trim(chunk_kind)) BETWEEN 3 AND 80),
    CHECK (char_length(trim(content)) >= 20),
    CHECK (jsonb_typeof(metadata_json) = 'object'),
    CHECK (position_in_document >= 1),
    CHECK (token_estimate >= 1),
    CHECK (checksum ~ '^[a-f0-9]{64}$')
);

CREATE TABLE IF NOT EXISTS rag.relations (
    id BIGSERIAL PRIMARY KEY,
    relation_id TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    evidence_text TEXT NOT NULL,
    source_document_id TEXT NOT NULL REFERENCES rag.documents(document_id) ON DELETE CASCADE,
    source_chunk_id TEXT NULL REFERENCES rag.chunks(chunk_id) ON DELETE SET NULL,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ingestion_run_id BIGINT NULL REFERENCES rag.ingestion_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (char_length(trim(relation_id)) BETWEEN 8 AND 120),
    CHECK (char_length(trim(source_type)) BETWEEN 2 AND 80),
    CHECK (char_length(trim(source_id)) BETWEEN 2 AND 180),
    CHECK (relation_type IN (
        'recommended_with',
        'contraindicated_with',
        'uses_component',
        'excludes',
        'routes_to',
        'compares_with',
        'supports_signal',
        'best_for_activity',
        'not_ideal_for_activity'
    )),
    CHECK (char_length(trim(target_type)) BETWEEN 2 AND 80),
    CHECK (char_length(trim(target_id)) BETWEEN 2 AND 180),
    CHECK (weight >= 0),
    CHECK (char_length(trim(evidence_text)) BETWEEN 1 AND 1000),
    CHECK (jsonb_typeof(metadata_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_rag_ingestion_runs_corpus_started_at
    ON rag.ingestion_runs (corpus_name, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_documents_knowledge_type
    ON rag.documents (knowledge_type);

CREATE INDEX IF NOT EXISTS idx_rag_documents_entity_id
    ON rag.documents (entity_id);

CREATE INDEX IF NOT EXISTS idx_rag_documents_checksum
    ON rag.documents (checksum);

CREATE INDEX IF NOT EXISTS idx_rag_documents_ingestion_run
    ON rag.documents (ingestion_run_id);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_document_id
    ON rag.chunks (document_id);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_knowledge_type
    ON rag.chunks (knowledge_type);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_chunk_kind
    ON rag.chunks (chunk_kind);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_entity_id
    ON rag.chunks (entity_id);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_checksum
    ON rag.chunks (checksum);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_content_tsv
    ON rag.chunks USING GIN (content_tsv);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_metadata_json
    ON rag.chunks USING GIN (metadata_json jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw
    ON rag.chunks USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rag_relations_source
    ON rag.relations (source_type, source_id, relation_type);

CREATE INDEX IF NOT EXISTS idx_rag_relations_target
    ON rag.relations (target_type, target_id, relation_type);

CREATE INDEX IF NOT EXISTS idx_rag_relations_source_document
    ON rag.relations (source_document_id);

CREATE INDEX IF NOT EXISTS idx_rag_relations_metadata_json
    ON rag.relations USING GIN (metadata_json jsonb_path_ops);

DROP TRIGGER IF EXISTS trg_rag_documents_updated_at ON rag.documents;
CREATE TRIGGER trg_rag_documents_updated_at
BEFORE UPDATE ON rag.documents
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_rag_chunks_updated_at ON rag.chunks;
CREATE TRIGGER trg_rag_chunks_updated_at
BEFORE UPDATE ON rag.chunks
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DO $$
DECLARE
    target_role TEXT;
BEGIN
    FOR target_role IN
        SELECT DISTINCT grantee
        FROM information_schema.role_table_grants
        WHERE table_schema = current_schema()
          AND table_name IN ('students', 'schedule_profiles')
          AND privilege_type = 'INSERT'
          AND grantee <> 'PUBLIC'
    LOOP
        EXECUTE format('GRANT USAGE ON SCHEMA rag TO %I', target_role);
        EXECUTE format(
            'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA rag TO %I',
            target_role
        );
        EXECUTE format(
            'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA rag TO %I',
            target_role
        );
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I',
            target_role
        );
        EXECUTE format(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA rag GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO %I',
            target_role
        );
    END LOOP;
END $$;

COMMIT;
