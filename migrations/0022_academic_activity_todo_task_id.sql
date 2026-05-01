BEGIN;

-- Gap identificado en revisión pre-deploy: el campo todo_task_id del schema
-- Pydantic AcademicActivity no tenía columna correspondiente en DB.
-- Sin esta columna el vínculo actividad→Microsoft To Do solo vivía en el
-- checkpoint de LangGraph y se perdía al resetear la conversación.

ALTER TABLE academic_activities
    ADD COLUMN IF NOT EXISTS todo_task_id TEXT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_academic_activities_todo_task_id'
          AND conrelid = 'academic_activities'::regclass
    ) THEN
        ALTER TABLE academic_activities
            ADD CONSTRAINT ck_academic_activities_todo_task_id
            CHECK (todo_task_id IS NULL OR char_length(trim(todo_task_id)) BETWEEN 1 AND 500);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_academic_activities_todo_task_id
    ON academic_activities (todo_task_id)
    WHERE todo_task_id IS NOT NULL;

COMMIT;