CREATE TABLE IF NOT EXISTS teacher_draft_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK(status IN ('draft', 'reviewed')),
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES workflow_runs(id) ON DELETE CASCADE,
    UNIQUE(run_id, version)
);

CREATE INDEX IF NOT EXISTS idx_teacher_drafts_run_version
    ON teacher_draft_versions(run_id, version DESC);
