BEGIN;

ALTER TABLE study_personalization_scores
    ADD COLUMN IF NOT EXISTS max_score INTEGER;

ALTER TABLE study_personalization_scores
    ADD COLUMN IF NOT EXISTS normalized_score NUMERIC(6,4);

WITH payload_scores AS (
    SELECT
        profile.id AS profile_id,
        score_item ->> 'technique_id' AS technique_id,
        NULLIF(score_item ->> 'max_score', '')::INTEGER AS max_score,
        NULLIF(score_item ->> 'normalized_score', '')::NUMERIC(6,4) AS normalized_score
    FROM study_personalization_profiles AS profile
    CROSS JOIN LATERAL jsonb_array_elements(
        CASE
            WHEN jsonb_typeof(profile.result_payload -> 'scores') = 'array'
                THEN profile.result_payload -> 'scores'
            ELSE '[]'::jsonb
        END
    ) AS score_item
)
UPDATE study_personalization_scores AS stored_score
SET max_score = COALESCE(payload_scores.max_score, stored_score.max_score),
    normalized_score = COALESCE(
        payload_scores.normalized_score,
        stored_score.normalized_score
    )
FROM payload_scores
WHERE stored_score.personalization_profile_id = payload_scores.profile_id
  AND stored_score.technique_id = payload_scores.technique_id;

UPDATE study_personalization_scores
SET max_score = COALESCE(max_score, 0);

UPDATE study_personalization_scores
SET normalized_score = COALESCE(
    normalized_score,
    CASE
        WHEN max_score > 0 THEN ROUND(score::NUMERIC / max_score::NUMERIC, 4)
        ELSE 0::NUMERIC
    END
);

ALTER TABLE study_personalization_scores
    ALTER COLUMN max_score SET DEFAULT 0;

ALTER TABLE study_personalization_scores
    ALTER COLUMN normalized_score SET DEFAULT 0.0;

ALTER TABLE study_personalization_scores
    ALTER COLUMN max_score SET NOT NULL;

ALTER TABLE study_personalization_scores
    ALTER COLUMN normalized_score SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_study_personalization_scores_max_score_nonnegative'
    ) THEN
        ALTER TABLE study_personalization_scores
            ADD CONSTRAINT chk_study_personalization_scores_max_score_nonnegative
            CHECK (max_score >= 0);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_study_personalization_scores_normalized_score_range'
    ) THEN
        ALTER TABLE study_personalization_scores
            ADD CONSTRAINT chk_study_personalization_scores_normalized_score_range
            CHECK (normalized_score >= 0 AND normalized_score <= 1.0000);
    END IF;
END $$;

COMMENT ON COLUMN study_personalization_scores.score IS
    'Legacy raw_score del scoring determinista del Radar de estudio.';

COMMENT ON COLUMN study_personalization_scores.max_score IS
    'Maximo score alcanzable para la tecnica dentro de la version del cuestionario usada.';

COMMENT ON COLUMN study_personalization_scores.normalized_score IS
    'Score normalizado entre 0 y 1 usado para ranking y analitica.';

UPDATE study_personalization_answers
SET option_id = NULL
WHERE option_id IS NOT NULL
  AND answer_value ->> 'answer_stage' = 'radar';

WITH cleaned_activation_reasons AS (
    SELECT
        profile.id,
        TO_JSONB(
            COALESCE(
                ARRAY_REMOVE(
                    ARRAY[
                        CASE
                            WHEN COALESCE(
                                (profile.result_payload #>> '{tiebreaker,assessment,uniform_response}')::BOOLEAN,
                                FALSE
                            ) THEN 'uniform_answers'
                        END,
                        CASE
                            WHEN COALESCE(
                                (profile.result_payload #>> '{tiebreaker,assessment,score_tie}')::BOOLEAN,
                                FALSE
                            ) THEN 'full_score_tie'
                        END,
                        CASE
                            WHEN NOT COALESCE(
                                (profile.result_payload #>> '{tiebreaker,assessment,score_tie}')::BOOLEAN,
                                FALSE
                            )
                            AND COALESCE(
                                profile.result_payload #>> '{tiebreaker,assessment,profile_confidence}',
                                ''
                            ) = 'baja'
                            AND COALESCE(
                                (profile.result_payload #>> '{tiebreaker,assessment,top_gap}')::NUMERIC,
                                0
                            ) <= 0.10
                                THEN 'low_gap_between_top_scores'
                        END
                    ]::TEXT[],
                    NULL
                ),
                ARRAY[]::TEXT[]
            )
        ) AS activation_reasons
    FROM study_personalization_profiles AS profile
    WHERE profile.result_payload #> '{tiebreaker,assessment}' IS NOT NULL
)
UPDATE study_personalization_profiles AS profile
SET result_payload = JSONB_SET(
    profile.result_payload,
    '{tiebreaker,assessment,activation_reasons}',
    cleaned_activation_reasons.activation_reasons,
    TRUE
)
FROM cleaned_activation_reasons
WHERE profile.id = cleaned_activation_reasons.id;

COMMIT;
