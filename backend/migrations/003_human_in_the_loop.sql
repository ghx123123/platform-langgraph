-- 人在回路：暂停时保存待处理输入的描述
ALTER TABLE workflow_runs ADD COLUMN pending_input_json TEXT;
