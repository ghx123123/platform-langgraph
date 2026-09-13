-- Additive Blueprint fields.  Existing LessonVersion rows remain readable.
ALTER TABLE lesson_versions ADD COLUMN knowledge_points_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE speaker_note_blocks ADD COLUMN knowledge_point_ids_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE interaction_anchors ADD COLUMN after_block_id TEXT;
ALTER TABLE interaction_anchors ADD COLUMN knowledge_point_ids_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE interaction_anchors ADD COLUMN priority INTEGER NOT NULL DEFAULT 1 CHECK(priority >= 0 AND priority <= 10);
ALTER TABLE expected_misconceptions ADD COLUMN knowledge_point_id TEXT;
ALTER TABLE expected_misconceptions ADD COLUMN observable_signals_json TEXT NOT NULL DEFAULT '[]';
ALTER TABLE expected_misconceptions ADD COLUMN recommended_correction TEXT;

CREATE INDEX IF NOT EXISTS idx_interaction_anchors_after_block
    ON interaction_anchors(lesson_slide_id, after_block_id);
CREATE INDEX IF NOT EXISTS idx_misconceptions_knowledge_point
    ON expected_misconceptions(lesson_slide_id, knowledge_point_id);
