BEGIN;

ALTER TABLE reminder_policies
    DROP CONSTRAINT IF EXISTS reminder_policies_reminder_type_check;

ALTER TABLE reminder_policies
    ADD CONSTRAINT reminder_policies_reminder_type_check
    CHECK (
        reminder_type IN (
            'pre_session',
            'followup',
            'missed_session',
            'daily_agenda',
            'activity_due',
            'activity_overdue'
        )
    );

COMMIT;
