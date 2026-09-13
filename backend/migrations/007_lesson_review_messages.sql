-- Preparation-stage Teacher/User review history. ClassroomEvent remains
-- reserved for the actual simulated classroom.
CREATE TABLE IF NOT EXISTS lesson_review_messages (
    message_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    slide_id TEXT,
    role TEXT NOT NULL CHECK(role IN ('user', 'teacher', 'system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(version_id) REFERENCES lesson_versions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lesson_review_messages_version
    ON lesson_review_messages(run_id, version_id, created_at);
