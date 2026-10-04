"""Creator formats v1. Rule text is data, never executable Python or JavaScript."""
import json
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .common import Contract, Extensible, Metadata

RULE_SYSTEM = Literal['ember-light/v1', 'dnd5e-srd-5.2.1/v1', 'ember-coop-settlement/v1']
COLOR = Annotated[str, Field(pattern=r'^#[0-9a-fA-F]{6}$')]
MAX_WORLD_BYTES = 384 * 1024


class Attributes(Contract):
    strength: int = Field(default=0, ge=-3, le=5)
    dexterity: int = Field(default=0, ge=-3, le=5)
    knowledge: int = Field(default=0, ge=-3, le=5)
    insight: int = Field(default=0, ge=-3, le=5)
    charisma: int = Field(default=0, ge=-3, le=5)


class CharacterData(Extensible):
    name: str = Field(min_length=1, max_length=32)
    archetype: str = Field(default='旅人', min_length=1, max_length=32)
    description: str = Field(default='', max_length=1000)
    gm_notes: str = Field(default='', max_length=2000)
    avatar: Literal['feather', 'shield', 'sword', 'book', 'spark'] = 'feather'
    hp: int = Field(default=12, ge=0, le=100)
    max_hp: int = Field(default=12, ge=1, le=100)
    stress: int = Field(default=0, ge=0, le=6)
    attributes: Attributes = Field(default_factory=Attributes)
    inventory: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(default_factory=list, max_length=24)

    @field_validator('inventory')
    @classmethod
    def clean_items(cls, value):
        if any(not item.strip() for item in value):
            raise ValueError('物品不能为空')
        return [item.strip() for item in value]

    @model_validator(mode='after')
    def hp_range(self):
        if self.hp > self.max_hp:
            raise ValueError('当前生命不能超过生命上限')
        return self


class LoreEntry(Contract):
    id: str = Field(default='', max_length=64, pattern=r'^[a-zA-Z0-9_-]*$')
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=3000)
    tags: str = Field(default='', max_length=120)
    keys: list[Annotated[str, Field(min_length=1, max_length=60)]] = Field(default_factory=list, max_length=24)
    kind: Literal['lore', 'rule'] = 'lore'
    visibility: Literal['public', 'gm'] = 'public'
    enabled: bool = True
    activation: Literal['keywords', 'always'] = 'keywords'
    priority: int = Field(default=0, ge=-100, le=100)


class WorldData(Extensible):
    """World data is limited to 384 KiB encoded UTF-8, in addition to field limits."""
    model_config = {**Extensible.model_config, 'json_schema_extra': {'x-max-bytes': MAX_WORLD_BYTES}}
    title: str = Field(min_length=1, max_length=80)
    premise: str = Field(min_length=1, max_length=4000)
    tone: str = Field(default='克制、神秘、有选择的代价', max_length=160)
    rule_system: RULE_SYSTEM = 'ember-light/v1'
    lore: list[LoreEntry] = Field(default_factory=list, max_length=160)

    @model_validator(mode='after')
    def world_integrity(self):
        ids = [entry.id for entry in self.lore if entry.id]
        if len(ids) != len(set(ids)):
            raise ValueError('世界书条目 ID 不能重复')
        if len(json.dumps(self.model_dump(mode='json', include=set(WorldData.model_fields)), ensure_ascii=False, separators=(',', ':')).encode()) > MAX_WORLD_BYTES:
            raise ValueError('整本世界设定数据不能超过 384 KiB，请缩短条目或拆分场景')
        return self


class Worldbook(Contract):
    format: Literal['ember.worldbook/v1']
    metadata: Metadata
    world: WorldData


class CharacterCard(Contract):
    format: Literal['ember.character/v1']
    metadata: Metadata
    rule_system: RULE_SYSTEM = 'ember-light/v1'
    character: CharacterData


class ThemePalette(Contract):
    # Aliases are the only CSS variables the host will ever apply.
    bg: COLOR = Field(alias='--bg')
    surface: COLOR = Field(alias='--surface')
    surface_2: COLOR = Field(alias='--surface-2')
    surface_3: COLOR = Field(alias='--surface-3')
    border: COLOR = Field(alias='--border')
    text: COLOR = Field(alias='--text')
    muted: COLOR = Field(alias='--muted')
    faint: COLOR = Field(alias='--faint')
    gold: COLOR = Field(alias='--gold')
    gold_hover: COLOR = Field(alias='--gold-hover')
    gold_bg: COLOR = Field(alias='--gold-bg')
    green: COLOR = Field(alias='--green')
    green_bg: COLOR = Field(alias='--green-bg')
    red: COLOR = Field(alias='--red')
    red_bg: COLOR = Field(alias='--red-bg')


class ThemeModes(Contract):
    dark: ThemePalette | None = None
    light: ThemePalette | None = None

    @model_validator(mode='after')
    def one_mode(self):
        if not self.dark and not self.light:
            raise ValueError('主题至少需要一种明暗配色')
        return self


class Theme(Contract):
    format: Literal['ember.theme/v1']
    metadata: Metadata
    modes: ThemeModes


CONTENT_MODELS = {'worldbook': Worldbook, 'character': CharacterCard, 'theme': Theme}
