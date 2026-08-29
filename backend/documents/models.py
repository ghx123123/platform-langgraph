from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


VisualBudget = Literal["small", "normal", "large"]
VisualElementType = Literal["diagram", "chart", "table", "formula", "image", "layout", "other"]


class DocumentVisualAnalysisRequest(BaseModel):
    page_number: int = Field(ge=1, le=500)
    budget: VisualBudget = "normal"
    extracted_text: str = Field(default="", max_length=6000)
    dry_run: bool = False


class DocumentVisualElement(BaseModel):
    type: VisualElementType = "other"
    title: str = Field(default="视觉内容", max_length=80)
    description: str = Field(default="", max_length=500)


class DocumentOcrCorrection(BaseModel):
    recognized: str = Field(default="", max_length=160)
    corrected: str = Field(default="", max_length=160)
    evidence: str = Field(default="", max_length=300)


class DocumentVisualAnalysis(BaseModel):
    page_number: int = Field(ge=1)
    status: Literal["completed", "dry_run"] = "completed"
    model: str
    budget: VisualBudget
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)
    image_bytes: int = Field(ge=1)
    response_ms: int = Field(default=0, ge=0)
    summary: str = Field(default="", max_length=1000)
    visual_elements: list[DocumentVisualElement] = Field(default_factory=list, max_length=12)
    teaching_notes: list[str] = Field(default_factory=list, max_length=10)
    ocr_corrections: list[DocumentOcrCorrection] = Field(default_factory=list, max_length=10)
    confidence: float = Field(default=0.0, ge=0, le=1)
    warnings: list[str] = Field(default_factory=list, max_length=10)
    analyzed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


class DocumentVisualAnalysisList(BaseModel):
    items: list[DocumentVisualAnalysis] = Field(default_factory=list)
