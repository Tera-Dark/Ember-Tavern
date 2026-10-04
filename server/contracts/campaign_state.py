"""Typed, bounded campaign-state records; never executable author code."""
from typing import Literal
from pydantic import Field, model_validator

from .common import Contract


Visibility = Literal['public', 'gm']
_RECORD_ID = r'^[a-z][a-z0-9_-]{2,39}$'


class QuestRecord(Contract):
    id: str = Field(pattern=_RECORD_ID)
    title: str = Field(min_length=1, max_length=80)
    summary: str = Field(default='', max_length=600)
    status: Literal['proposed', 'active', 'paused', 'completed', 'failed'] = 'proposed'
    visibility: Visibility = 'public'


class NPCRecord(Contract):
    id: str = Field(pattern=_RECORD_ID)
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(default='', max_length=80)
    summary: str = Field(default='', max_length=600)
    status: Literal['unknown', 'present', 'missing', 'deceased', 'ally', 'neutral', 'hostile'] = 'unknown'
    relationship: int = Field(default=0, ge=-5, le=5)
    visibility: Visibility = 'public'


class ResourceRecord(Contract):
    id: str = Field(pattern=_RECORD_ID)
    name: str = Field(min_length=1, max_length=80)
    value: int = Field(ge=-1_000_000, le=1_000_000)
    minimum: int = Field(default=0, ge=-1_000_000, le=1_000_000)
    maximum: int = Field(default=1_000, ge=-1_000_000, le=1_000_000)
    unit: str = Field(default='', max_length=24)
    visibility: Visibility = 'public'

    @model_validator(mode='after')
    def bounded_value(self):
        if self.minimum > self.maximum:
            raise ValueError('资源下限不能大于上限')
        if not self.minimum <= self.value <= self.maximum:
            raise ValueError('资源当前值必须在声明范围内')
        return self


class CampaignState(Contract):
    format: Literal['ember.campaign-state/v1'] = 'ember.campaign-state/v1'
    quests: list[QuestRecord] = Field(default_factory=list, max_length=64)
    npcs: list[NPCRecord] = Field(default_factory=list, max_length=64)
    resources: list[ResourceRecord] = Field(default_factory=list, max_length=64)

    @model_validator(mode='after')
    def bounded_unique_records(self):
        for label, values in (('任务', self.quests), ('NPC', self.npcs), ('资源', self.resources)):
            ids = [item.id for item in values]
            if len(ids) != len(set(ids)):
                raise ValueError(f'{label} ID 不能重复')
        if sum(map(len, (self.quests, self.npcs, self.resources))) > 120:
            raise ValueError('单个战役最多保存 120 条结构化状态')
        return self
