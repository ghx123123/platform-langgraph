"""Patch-based lesson revision and multi-round version management (Phase 5)."""
from __future__ import annotations

import copy
import json
import re
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from .models import (
    LessonVersion,
    RevisionPatch,
    SimulationRound,
    StudentCognitiveState,
    StudentPersona,
    StudentScenarioBaseline,
    SupervisorObservation,
    SupervisorReport,
)
from .prompts import build_revision_prompt
from .repository import ClassroomRepository

Generator = Callable[[str, str], Awaitable[Any]]


class RevisionError(ValueError):
    pass


class RevisionEngine:
    """Generate, validate, apply and persist minimal RevisionPatch objects."""

    def __init__(self, repository: ClassroomRepository, generator: Generator | None = None, *, mode: str = "AUTO_APPLY") -> None:
        self.repository = repository
        self.generator = generator
        self.mode = mode

    async def generate_patches(
        self,
        source_version: LessonVersion,
        report: SupervisorReport,
        round_item: SimulationRound,
        observations: Sequence[SupervisorObservation] | None = None,
    ) -> list[RevisionPatch]:
        self._check_scope(source_version, report, round_item)
        obs = list(observations) if observations is not None else await self.repository.list_supervisor_observations(round_item.id)
        self._validate_observations(obs, round_item)
        context = {
            "source_version": source_version.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
            "observations": [item.model_dump(mode="json") for item in obs],
        }
        payload: Any = None
        if self.generator is not None:
            system, user = build_revision_prompt(context)
            payload = _parse_json(await self.generator(system, user))
        if payload is None:
            return self._fallback_patches(source_version, obs, round_item)
        if isinstance(payload, dict):
            payload = payload.get("patches", payload.get("items", []))
        if not isinstance(payload, list):
            raise RevisionError("revision output must be a JSON array")
        result: list[RevisionPatch] = []
        for item in payload:
            if isinstance(item, RevisionPatch):
                patch = item
            else:
                raw_item = dict(item)
                raw_item.update({
                    "patch_id": raw_item.get("patch_id") or str(uuid4()),
                    "run_id": source_version.run_id,
                    "source_version_id": source_version.id,
                    "source_round_id": round_item.id,
                })
                patch = RevisionPatch.model_validate(raw_item)
            result.append(patch)
        return result

    async def create_patches(self, *args: Any, **kwargs: Any) -> list[RevisionPatch]:
        return await self.generate_patches(*args, **kwargs)

    async def apply_patches(
        self,
        source_version: LessonVersion,
        round_item: SimulationRound,
        patches: Sequence[RevisionPatch],
        *,
        persist: bool = True,
    ) -> LessonVersion:
        """Atomically validate all patches in memory, then persist V2 once."""
        if source_version.run_id != round_item.run_id:
            raise RevisionError("source version and round belong to different runs")
        target_id = str(uuid4())
        prepared: list[RevisionPatch] = []
        all_validated = False
        try:
            observations = await self.repository.list_supervisor_observations(round_item.id)
            for original in patches:
                patch = original.model_copy(update={"target_version_id": target_id})
                self.validate_patch(source_version, patch, round_item=round_item, observations=observations)
                prepared.append(patch)
            all_validated = True
            data = copy.deepcopy(source_version.model_dump(mode="python"))
            for patch in prepared:
                _apply_patch(data, patch)
            data.update({
                "id": target_id,
                "version_number": source_version.version_number + 1,
                "source_version_id": source_version.id,
                "created_from_round_id": round_item.id,
                "status": "ready",
                "updated_at": datetime.now(timezone.utc),
            })
            # Database row identities are new for the clone; semantic IDs used
            # by provenance (slide_id/block_id/interaction_id/misconception_id)
            # remain stable across versions.
            for slide_data in data.get("slides", []):
                slide_data["id"] = str(uuid4())
                for block_data in slide_data.get("speaker_notes", []):
                    block_data["id"] = str(uuid4())
                for anchor_data in slide_data.get("interaction_anchors", []):
                    anchor_data["id"] = str(uuid4())
            target = LessonVersion.model_validate(data)
            if persist:
                await self.repository.ensure_run(source_version.run_id)
                await self.repository.create_lesson_version(target)
                for patch in prepared:
                    await self.repository.save_revision_patch(patch.model_copy(update={"status": "applied", "applied_at": datetime.now(timezone.utc)}))
            return target
        except Exception as exc:
            # Failed revisions never write a partial target. Record failed patch
            # metadata where possible so the caller can retry and audit it.
            candidates = prepared if all_validated else [p for p in patches if p.patch_id not in {item.patch_id for item in prepared}]
            for patch in candidates:
                try:
                    failed = patch.model_copy(update={"target_version_id": target_id, "status": "failed"})
                    if persist:
                        await self.repository.save_revision_patch(failed)
                except Exception:
                    pass
            if isinstance(exc, RevisionError):
                raise
            raise RevisionError(f"revision failed; source version was preserved: {exc}") from exc

    async def clone_and_apply(self, *args: Any, **kwargs: Any) -> LessonVersion:
        return await self.apply_patches(*args, **kwargs)

    def validate_revision_patch(self, *args: Any, **kwargs: Any) -> None:
        self.validate_patch(*args, **kwargs)

    async def refine_round(
        self,
        source_version: LessonVersion,
        round_item: SimulationRound,
        report: SupervisorReport,
        *,
        max_rounds: int,
        observations: Sequence[SupervisorObservation] | None = None,
    ) -> tuple[LessonVersion, list[RevisionPatch], bool]:
        """Return (current version, patches, finalized). Last round creates no V(n+1)."""
        if round_item.round_number >= max_rounds:
            final = source_version.model_copy(update={"status": "final", "updated_at": datetime.now(timezone.utc)})
            await self.repository.update_lesson_version_status(source_version.id, "final")
            return final, [], True
        patches = await self.generate_patches(source_version, report, round_item, observations)
        if self.mode != "AUTO_APPLY":
            # Manual-review mode is data-only in Phase 5: keep proposals
            # pending and let a later approval boundary call apply_patches.
            for patch in patches:
                await self.repository.save_revision_patch(patch.model_copy(update={"status": "pending"}))
            return source_version, patches, False
        if not patches:
            # Still create a version boundary for the next rehearsal while
            # retaining every stable id and field.
            return await self.apply_patches(source_version, round_item, [], persist=True), [], False
        target = await self.apply_patches(source_version, round_item, patches, persist=True)
        return target, patches, False

    async def initialize_round_cognitive_states(
        self,
        run_id: str,
        round_item: SimulationRound,
        personas: Sequence[StudentPersona],
        knowledge_point_ids: Sequence[str],
    ) -> list[StudentCognitiveState]:
        """Create fresh runtime states from the immutable baseline for a round."""
        if round_item.run_id != run_id:
            raise RevisionError("run_id and round do not match")
        result: list[StudentCognitiveState] = []
        for persona in personas:
            if persona.run_id != run_id:
                raise RevisionError("persona belongs to another run")
            baseline = await self.repository.get_student_scenario_baseline(run_id, persona.student_id)
            if baseline is None:
                baseline = StudentScenarioBaseline(
                    run_id=run_id, student_id=persona.student_id,
                    initial_mastery={kp: 0.5 for kp in knowledge_point_ids},
                    initial_confidence={kp: persona.confidence for kp in knowledge_point_ids},
                    initial_misconceptions=persona.misconception_profile,
                    prior_knowledge=persona.prior_knowledge, scenario_seed=round_item.scenario_seed,
                )
                await self.repository.save_student_scenario_baseline(baseline)
            elif baseline.scenario_seed != round_item.scenario_seed:
                raise RevisionError("scenario seed must remain stable across rounds")
            for kp in knowledge_point_ids or ["general"]:
                state = StudentCognitiveState(
                    round_id=round_item.id, student_id=persona.student_id, knowledge_point_id=kp,
                    current_mastery=float(baseline.initial_mastery.get(kp, 0.5)),
                    current_confidence=float(baseline.initial_confidence.get(kp, persona.confidence)),
                    misconceptions=_misconceptions_for(baseline.initial_misconceptions, kp),
                )
                await self.repository.save_student_cognitive_state(state)
                result.append(state)
        return result

    def validate_patch(self, source: LessonVersion, patch: RevisionPatch, *, round_item: SimulationRound | None = None, observations: Sequence[SupervisorObservation] | None = None) -> None:
        if patch.run_id != source.run_id or patch.source_version_id != source.id:
            raise RevisionError("patch crosses run or source version boundary")
        if round_item is not None and (patch.source_round_id != round_item.id or round_item.run_id != source.run_id):
            raise RevisionError("patch source round does not match source version")
        slide = next((s for s in source.slides if s.slide_id == patch.slide_id), None)
        if slide is None:
            raise RevisionError(f"target slide does not exist: {patch.slide_id}")
        if patch.target_type == "speaker_note" and (patch.block_id is None or not any(b.block_id == patch.block_id for b in slide.speaker_notes)):
            raise RevisionError(f"target block does not exist: {patch.block_id}")
        if patch.target_type == "interaction_anchor" and (patch.block_id is None or not any(a.interaction_id == patch.block_id or a.id == patch.block_id for a in slide.interaction_anchors)):
            raise RevisionError(f"target interaction does not exist: {patch.block_id}")
        if patch.target_type == "misconception" and (patch.block_id is None or not any(m.misconception_id == patch.block_id for m in slide.expected_misconceptions)):
            raise RevisionError(f"target misconception does not exist: {patch.block_id}")
        if not _allowed_path(patch.target_type, patch.field_path):
            raise RevisionError(f"field path is not editable: {patch.field_path}")
        if not patch.source_observation_ids:
            raise RevisionError("patch must cite at least one source observation")
        actual = _get_target_value(source, patch)
        if actual != patch.before:
            raise RevisionError(f"patch before value does not match source for {patch.field_path}")
        if observations is not None:
            self._validate_observations(observations, round_item)
            valid = {o.observation_id for o in observations}
            if not set(patch.source_observation_ids) <= valid:
                raise RevisionError("patch references unknown observation")

    @staticmethod
    def _check_scope(source: LessonVersion, report: SupervisorReport, round_item: SimulationRound) -> None:
        if source.run_id != report.run_id or source.run_id != round_item.run_id or report.round_id != round_item.id:
            raise RevisionError("source, report and round must share run and round scope")

    @staticmethod
    def _validate_observations(observations: Sequence[SupervisorObservation], round_item: SimulationRound | None) -> None:
        if round_item is not None and any(o.round_id != round_item.id for o in observations):
            raise RevisionError("observation belongs to another round")

    @staticmethod
    def _fallback_patches(source: LessonVersion, observations: Sequence[SupervisorObservation], round_item: SimulationRound) -> list[RevisionPatch]:
        result: list[RevisionPatch] = []
        for obs in observations:
            if obs.severity not in {"major", "critical"}:
                continue
            slide = next((s for s in source.slides if s.slide_id == obs.slide_id), None)
            if slide is None or not slide.speaker_notes:
                continue
            block = slide.speaker_notes[0]
            before = block.content
            after = before + f"\n[Clarification] {obs.recommendation}"
            result.append(RevisionPatch(run_id=source.run_id, source_version_id=source.id, source_round_id=round_item.id, target_type="speaker_note", slide_id=slide.slide_id, block_id=block.block_id, field_path="content", before=before, after=after, reason=obs.issue, source_observation_ids=[obs.observation_id]))
        return result


def _allowed_path(target_type: str, path: str) -> bool:
    path = path.removeprefix("slide.") if target_type == "slide" else path
    if target_type == "slide":
        return path in {"title", "purpose", "estimated_minutes", "learning_objectives", "knowledge_points", "ppt_content", "ppt_content.title", "ppt_content.subtitle", "ppt_content.bullets", "ppt_content.examples", "ppt_content.code_blocks", "ppt_content.visual_instruction"}
    if target_type == "speaker_note":
        return path.removeprefix("speaker_note_block.").removeprefix("speaker_notes.") in {"content", "estimated_seconds", "block_type", "knowledge_point_ids"}
    if target_type == "interaction_anchor":
        return path.removeprefix("interaction_anchor.") in {"type", "objective", "planned_question", "target_student_level", "after_block_id", "knowledge_point_ids", "priority", "max_questions"}
    if target_type == "misconception":
        return path.removeprefix("expected_misconception.").removeprefix("misconception.") in {"description", "correction_strategy", "knowledge_point_id", "observable_signals", "recommended_correction"}
    return path in {"title", "learning_objectives", "knowledge_points", "estimated_minutes"}


def _get_target_value(source: LessonVersion, patch: RevisionPatch) -> Any:
    slide = next(s for s in source.slides if s.slide_id == patch.slide_id)
    if patch.target_type == "slide":
        obj: Any = slide.model_dump(mode="python")
        path = patch.field_path.removeprefix("slide.")
    elif patch.target_type == "speaker_note":
        obj = next(b for b in slide.speaker_notes if b.block_id == patch.block_id).model_dump(mode="python")
        path = patch.field_path.removeprefix("speaker_note_block.").removeprefix("speaker_notes.")
    elif patch.target_type == "interaction_anchor":
        obj = next(a for a in slide.interaction_anchors if a.interaction_id == patch.block_id or a.id == patch.block_id).model_dump(mode="python")
        path = patch.field_path.removeprefix("interaction_anchor.")
    elif patch.target_type == "misconception":
        obj = next(m for m in slide.expected_misconceptions if m.misconception_id == patch.block_id).model_dump(mode="python")
        path = patch.field_path.removeprefix("expected_misconception.").removeprefix("misconception.")
    else:
        obj = source.model_dump(mode="python"); path = patch.field_path
    for part in path.split("."):
        obj = obj[part]
    return obj


def _apply_patch(data: dict[str, Any], patch: RevisionPatch) -> None:
    slide = next(s for s in data["slides"] if s["slide_id"] == patch.slide_id)
    if patch.target_type == "slide":
        obj: Any = slide; path = patch.field_path.removeprefix("slide.")
    elif patch.target_type == "speaker_note":
        obj = next(b for b in slide["speaker_notes"] if b["block_id"] == patch.block_id); path = patch.field_path.removeprefix("speaker_note_block.").removeprefix("speaker_notes.")
    elif patch.target_type == "interaction_anchor":
        obj = next(a for a in slide["interaction_anchors"] if a.get("interaction_id") == patch.block_id or a.get("id") == patch.block_id); path = patch.field_path.removeprefix("interaction_anchor.")
    elif patch.target_type == "misconception":
        obj = next(m for m in slide["expected_misconceptions"] if m.get("misconception_id") == patch.block_id); path = patch.field_path.removeprefix("expected_misconception.").removeprefix("misconception.")
    else:
        obj = data; path = patch.field_path
    parts = path.split(".")
    for part in parts[:-1]: obj = obj[part]
    obj[parts[-1]] = copy.deepcopy(patch.after)


def _misconceptions_for(values: dict[str, Any], kp: str) -> list[str]:
    value = values.get(kp, values.get("misconceptions", []))
    if isinstance(value, str): return [value]
    if isinstance(value, list): return [str(item) for item in value]
    return []


def _parse_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)): return raw
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(raw).strip(), flags=re.IGNORECASE)
    try: return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start: return json.loads(text[start:end + 1])
        raise RevisionError("revision output is not valid JSON")
