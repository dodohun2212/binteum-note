"""6장 JSON 형식 (pydantic v2). AI 답은 코드가 다듬은 뒤 이 형식으로 검사해 dict로 저장한다."""
from typing import List, Optional

from pydantic import BaseModel, Field


class Concept(BaseModel):
    id: str
    name: str
    summary: str = ""
    pages: List[int] = Field(default_factory=list)
    in_objectives: bool = False
    objective_quote: Optional[str] = None
    has_example: bool = False
    has_exercise: bool = False
    exercise_numbers: List[int] = Field(default_factory=list)
    keywords: List[str] = Field(default_factory=list)


class Utterance(BaseModel):
    concept_id: Optional[str] = None
    concept_name: str = ""
    quote: str
    type: str
    strength: int = Field(ge=1, le=3)


class RubricItem(BaseModel):
    point: str
    score: int = Field(ge=0, le=10)


class Question(BaseModel):
    kind: str                      # "서술형" / "객관식"
    question: str
    answer: str                    # 서술형: 모범 답안 / 객관식: 정답 보기 글
    rubric: List[RubricItem] = Field(default_factory=list)
    choices: List[str] = Field(default_factory=list)
    answer_index: Optional[int] = None
    explanation: str = ""
    source_pages: List[int] = Field(default_factory=list)
    figure: Optional[dict] = None


class Grading(BaseModel):
    kind: str
    score: int = Field(ge=0, le=10)
    max: int = 10
    status: str                    # 앎 / 헷갈림 / 모름
    error_type: Optional[str] = None
    reason: str = ""
    rubric_scores: List[int] = Field(default_factory=list)


class Explanation(BaseModel):
    concept_id: str
    my_gap: str = ""
    explanation: str
    check_pages: List[int] = Field(default_factory=list)
    source_pages: List[int] = Field(default_factory=list)
    not_found: bool = False
    not_found_note: Optional[str] = None
    confusion_reply: Optional[str] = None


class NoteSection(BaseModel):
    concept_id: str
    detail: str                    # 자세히 / 보통 / 짧게
    from_ai: bool = True
    summary: str
    key_points: List[str] = Field(default_factory=list)
    pitfalls: List[str] = Field(default_factory=list)
    source_pages: List[int] = Field(default_factory=list)
