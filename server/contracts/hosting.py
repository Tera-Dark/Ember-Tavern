"""Bounded GM diagnostics. Evidence is private; free-form prompt dumps are forbidden."""
from typing import Annotated, Literal
from pydantic import Field
from .common import Contract


class ProviderTrace(Contract):
    provider: str = Field(max_length=80)
    model: str = Field(max_length=256)
    duration_ms: int = Field(ge=0, le=86400000)


class SelectedEntry(Contract):
    id: str = Field(max_length=64)
    title: str = Field(max_length=80)
    visibility: Literal['public', 'gm']
    reason: Literal['rule', 'always', 'keyword', 'lexical']
    chars: int = Field(ge=0, le=96000)
    truncated: bool


class MemorySelection(Contract):
    included: bool = False
    source_event_ids: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=50)
    chars: int = Field(default=0, ge=0, le=8000)
    truncated: bool = False


class ContextSelection(Contract):
    budget_chars: int = Field(ge=0, le=96000)
    used_chars: int = Field(ge=0, le=96000)
    entries: list[SelectedEntry] = Field(default_factory=list, max_length=32)
    omitted_ids: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list, max_length=160)
    method: str = Field(max_length=160)
    context_chars: int = Field(ge=0, le=96000)
    context_budget_chars: int = Field(ge=0, le=96000)
    memory_summary: MemorySelection = Field(default_factory=MemorySelection)


class GMTrace(Contract):
    mode: str = Field(max_length=32)
    label: str = Field(default='', max_length=160)
    retrieval_count: int = Field(default=0, ge=0, le=1000)
    duration_ms: int = Field(default=0, ge=0, le=86400000)
    knowledge: ProviderTrace | None = None
    decision: ProviderTrace | None = None
    context_ids: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list, max_length=128)
    context_selection: ContextSelection | None = None
