-- Classroom v2 domain storage.  This migration is additive and deliberately
-- independent from the legacy workflow JSON columns.  classroom_runs is the
-- future adapter boundary to workflow_runs; the two tables are not coupled by
-- a foreign key so an empty classroom database can be initialized in tests.
CREATE TABLE IF NOT EXISTS classroom_runs (
    run_id TEXT PRIMARY KEY,
    workflow_run_id TEXT,
    workflow_version TEXT NOT NULL DEFAULT 'classroom_v2',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_classroom_runs_workflow
    ON classroom_runs(workflow_run_id);

CREATE TABLE IF NOT EXISTS lesson_versions (
    id TEXT PRIMARY KEY,
    lesson_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    version_number INTEGER NOT NULL CHECK(version_number >= 1),
    source_version_id TEXT,
    created_from_round_id TEXT,
    title TEXT NOT NULL,
    learning_objectives_json TEXT NOT NULL DEFAULT '[]',
    estimated_minutes INTEGER NOT NULL CHECK(estimated_minutes > 0),
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(source_version_id) REFERENCES lesson_versions(id) ON DELETE SET NULL,
    -- Version numbers are scoped to a classroom run.  The same lesson may be
    -- rehearsed independently in multiple runs without colliding.
    UNIQUE(run_id, version_number)
);

CREATE INDEX IF NOT EXISTS idx_lesson_versions_run_version
    ON lesson_versions(run_id, version_number DESC);

CREATE TABLE IF NOT EXISTS lesson_slides (
    id TEXT PRIMARY KEY,
    lesson_version_id TEXT NOT NULL,
    slide_id TEXT NOT NULL,
    slide_order INTEGER NOT NULL CHECK(slide_order >= 1),
    title TEXT NOT NULL,
    purpose TEXT NOT NULL DEFAULT '',
    learning_objectives_json TEXT NOT NULL DEFAULT '[]',
    knowledge_points_json TEXT NOT NULL DEFAULT '[]',
    estimated_minutes INTEGER NOT NULL CHECK(estimated_minutes > 0),
    ppt_content_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(lesson_version_id) REFERENCES lesson_versions(id) ON DELETE CASCADE,
    UNIQUE(lesson_version_id, slide_id),
    UNIQUE(lesson_version_id, slide_order)
);

CREATE INDEX IF NOT EXISTS idx_lesson_slides_version_order
    ON lesson_slides(lesson_version_id, slide_order);

CREATE TABLE IF NOT EXISTS speaker_note_blocks (
    id TEXT PRIMARY KEY,
    lesson_slide_id TEXT NOT NULL,
    block_id TEXT NOT NULL,
    block_order INTEGER NOT NULL CHECK(block_order >= 1),
    block_type TEXT NOT NULL,
    content TEXT NOT NULL,
    estimated_seconds INTEGER NOT NULL CHECK(estimated_seconds > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(lesson_slide_id) REFERENCES lesson_slides(id) ON DELETE CASCADE,
    UNIQUE(lesson_slide_id, block_id),
    UNIQUE(lesson_slide_id, block_order)
);

CREATE INDEX IF NOT EXISTS idx_speaker_note_blocks_slide_order
    ON speaker_note_blocks(lesson_slide_id, block_order);

CREATE TABLE IF NOT EXISTS interaction_anchors (
    id TEXT PRIMARY KEY,
    lesson_slide_id TEXT NOT NULL,
    interaction_id TEXT NOT NULL,
    anchor_type TEXT NOT NULL,
    objective TEXT NOT NULL,
    planned_question TEXT NOT NULL,
    target_student_level TEXT NOT NULL,
    max_questions INTEGER NOT NULL DEFAULT 1 CHECK(max_questions >= 0),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    FOREIGN KEY(lesson_slide_id) REFERENCES lesson_slides(id) ON DELETE CASCADE,
    UNIQUE(lesson_slide_id, interaction_id)
);

CREATE TABLE IF NOT EXISTS expected_misconceptions (
    id TEXT PRIMARY KEY,
    lesson_slide_id TEXT NOT NULL,
    misconception_id TEXT NOT NULL,
    description TEXT NOT NULL,
    correction_strategy TEXT NOT NULL,
    FOREIGN KEY(lesson_slide_id) REFERENCES lesson_slides(id) ON DELETE CASCADE,
    UNIQUE(lesson_slide_id, misconception_id)
);

CREATE TABLE IF NOT EXISTS student_personas (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    name TEXT NOT NULL,
    level TEXT NOT NULL,
    ability REAL NOT NULL CHECK(ability >= 0 AND ability <= 1),
    prior_knowledge_json TEXT NOT NULL DEFAULT '{}',
    engagement REAL NOT NULL CHECK(engagement >= 0 AND engagement <= 1),
    confidence REAL NOT NULL CHECK(confidence >= 0 AND confidence <= 1),
    verbosity REAL NOT NULL CHECK(verbosity >= 0 AND verbosity <= 1),
    question_propensity REAL NOT NULL CHECK(question_propensity >= 0 AND question_propensity <= 1),
    answer_propensity REAL NOT NULL CHECK(answer_propensity >= 0 AND answer_propensity <= 1),
    misconception_profile_json TEXT NOT NULL DEFAULT '{}',
    scenario_seed TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE,
    UNIQUE(run_id, student_id)
);

CREATE TABLE IF NOT EXISTS student_scenario_baselines (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    initial_mastery_json TEXT NOT NULL DEFAULT '{}',
    initial_confidence_json TEXT NOT NULL DEFAULT '{}',
    initial_misconceptions_json TEXT NOT NULL DEFAULT '{}',
    prior_knowledge_json TEXT NOT NULL DEFAULT '{}',
    scenario_seed TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE,
    UNIQUE(run_id, student_id)
);

CREATE TABLE IF NOT EXISTS simulation_rounds (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    round_number INTEGER NOT NULL CHECK(round_number >= 1),
    lesson_version_id TEXT NOT NULL,
    scenario_seed TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    current_slide_id TEXT,
    current_slide_index INTEGER NOT NULL DEFAULT 0 CHECK(current_slide_index >= 0),
    virtual_elapsed_seconds INTEGER NOT NULL DEFAULT 0 CHECK(virtual_elapsed_seconds >= 0),
    started_at TEXT,
    completed_at TEXT,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(lesson_version_id) REFERENCES lesson_versions(id) ON DELETE RESTRICT,
    UNIQUE(run_id, round_number)
);

CREATE INDEX IF NOT EXISTS idx_simulation_rounds_run_number
    ON simulation_rounds(run_id, round_number);

CREATE TABLE IF NOT EXISTS classroom_states (
    round_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    phase TEXT NOT NULL,
    current_slide_id TEXT,
    current_slide_index INTEGER NOT NULL DEFAULT 0 CHECK(current_slide_index >= 0),
    current_block_id TEXT,
    active_agent_id TEXT,
    turn_count INTEGER NOT NULL DEFAULT 0 CHECK(turn_count >= 0),
    followup_depth INTEGER NOT NULL DEFAULT 0 CHECK(followup_depth >= 0),
    slide_interaction_count INTEGER NOT NULL DEFAULT 0 CHECK(slide_interaction_count >= 0),
    student_question_count INTEGER NOT NULL DEFAULT 0 CHECK(student_question_count >= 0),
    virtual_elapsed_seconds INTEGER NOT NULL DEFAULT 0 CHECK(virtual_elapsed_seconds >= 0),
    status TEXT NOT NULL DEFAULT 'active',
    state_version INTEGER NOT NULL DEFAULT 0 CHECK(state_version >= 0),
    updated_at TEXT NOT NULL,
    FOREIGN KEY(round_id) REFERENCES simulation_rounds(id) ON DELETE CASCADE,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_classroom_states_run
    ON classroom_states(run_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS classroom_agent_instances (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_key TEXT NOT NULL,
    role TEXT NOT NULL,
    display_name TEXT NOT NULL,
    student_id TEXT,
    persona_id TEXT,
    status TEXT NOT NULL DEFAULT 'configured',
    config_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(persona_id) REFERENCES student_personas(id) ON DELETE SET NULL,
    UNIQUE(run_id, agent_key)
);

CREATE TABLE IF NOT EXISTS student_cognitive_states (
    id TEXT PRIMARY KEY,
    round_id TEXT NOT NULL,
    student_id TEXT NOT NULL,
    knowledge_point_id TEXT NOT NULL,
    current_mastery REAL NOT NULL CHECK(current_mastery >= 0 AND current_mastery <= 1),
    current_confidence REAL NOT NULL CHECK(current_confidence >= 0 AND current_confidence <= 1),
    misconceptions_json TEXT NOT NULL DEFAULT '[]',
    resolved_misconceptions_json TEXT NOT NULL DEFAULT '[]',
    engagement_runtime REAL NOT NULL DEFAULT 0.5 CHECK(engagement_runtime >= 0 AND engagement_runtime <= 1),
    last_event_id TEXT,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(round_id) REFERENCES simulation_rounds(id) ON DELETE CASCADE,
    UNIQUE(round_id, student_id, knowledge_point_id)
);

CREATE INDEX IF NOT EXISTS idx_student_states_round_student
    ON student_cognitive_states(round_id, student_id);

CREATE TABLE IF NOT EXISTS classroom_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    round_id TEXT NOT NULL,
    slide_id TEXT,
    sequence INTEGER NOT NULL CHECK(sequence >= 1),
    actor_id TEXT NOT NULL,
    actor_role TEXT NOT NULL,
    event_type TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    reply_to TEXT,
    target_agent_id TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    virtual_timestamp INTEGER NOT NULL DEFAULT 0 CHECK(virtual_timestamp >= 0),
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(round_id) REFERENCES simulation_rounds(id) ON DELETE CASCADE,
    UNIQUE(run_id, sequence)
);

CREATE INDEX IF NOT EXISTS idx_classroom_events_round_sequence
    ON classroom_events(round_id, sequence);
CREATE INDEX IF NOT EXISTS idx_classroom_events_round_slide
    ON classroom_events(round_id, slide_id, sequence);
CREATE INDEX IF NOT EXISTS idx_classroom_events_actor
    ON classroom_events(run_id, actor_id, sequence);

CREATE TABLE IF NOT EXISTS supervisor_observations (
    observation_id TEXT PRIMARY KEY,
    round_id TEXT NOT NULL,
    slide_id TEXT NOT NULL,
    event_ids_json TEXT NOT NULL DEFAULT '[]',
    category TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    issue TEXT NOT NULL,
    evidence TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(round_id) REFERENCES simulation_rounds(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_supervisor_observations_round_slide
    ON supervisor_observations(round_id, slide_id, created_at);

CREATE TABLE IF NOT EXISTS supervisor_reports (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    round_id TEXT NOT NULL UNIQUE,
    overall_score INTEGER NOT NULL CHECK(overall_score >= 0 AND overall_score <= 100),
    dimension_scores_json TEXT NOT NULL DEFAULT '{}',
    strengths_json TEXT NOT NULL DEFAULT '[]',
    critical_issues_json TEXT NOT NULL DEFAULT '[]',
    observations_json TEXT NOT NULL DEFAULT '[]',
    revision_priorities_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(round_id) REFERENCES simulation_rounds(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS revision_patches (
    patch_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_version_id TEXT NOT NULL,
    target_version_id TEXT,
    source_round_id TEXT,
    target_type TEXT NOT NULL,
    slide_id TEXT NOT NULL,
    block_id TEXT,
    field_path TEXT NOT NULL,
    before_json TEXT NOT NULL,
    after_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_observation_ids_json TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'proposed',
    created_at TEXT NOT NULL,
    applied_at TEXT,
    FOREIGN KEY(run_id) REFERENCES classroom_runs(run_id) ON DELETE CASCADE,
    FOREIGN KEY(source_version_id) REFERENCES lesson_versions(id) ON DELETE RESTRICT,
    FOREIGN KEY(target_version_id) REFERENCES lesson_versions(id) ON DELETE SET NULL,
    FOREIGN KEY(source_round_id) REFERENCES simulation_rounds(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_revision_patches_source_round
    ON revision_patches(source_round_id, created_at);
CREATE INDEX IF NOT EXISTS idx_revision_patches_target_version
    ON revision_patches(target_version_id, status);
