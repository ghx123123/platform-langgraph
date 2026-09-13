-- Structured, evidence-based analysis for new Supervisor observations.
-- Existing observations remain readable with an empty JSON object.
ALTER TABLE supervisor_observations ADD COLUMN analysis_json TEXT NOT NULL DEFAULT '{}';
