-- Teacher directives: user input during classroom rehearsal becomes a first-class
-- constraint that later agent turns must honour, and (for intent=correct) can
-- produce revision patches.  Additive; older runs simply have no rows.
CREATE TABLE IF NOT EXISTS teacher_directives (
    directive_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    round_id TEXT NOT NULL,
    slide_id TEXT,
    source_event_id TEXT NOT NULL,
    content TEXT NOT NULL,
    intent TEXT NOT NULL DEFAULT 'question',
    scope TEXT NOT NULL DEFAULT 'round',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_teacher_directives_round
    ON teacher_directives(round_id, status);

CREATE INDEX IF NOT EXISTS idx_teacher_directives_run
    ON teacher_directives(run_id, status);

-- Revision patches may now originate from a teacher intervention instead of a
-- supervisor observation; keep the provenance so the review UI can trace back.
ALTER TABLE revision_patches ADD COLUMN source_intervention_ids_json TEXT NOT NULL DEFAULT '[]';
