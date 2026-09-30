from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
import re

Attribute = Literal['strength', 'dexterity', 'knowledge', 'insight', 'charisma']

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class Register(StrictModel):
    username: str = Field(min_length=3, max_length=24, pattern=r'^[a-zA-Z0-9_]+$')
    display_name: str = Field(min_length=1, max_length=24)
    password: str = Field(min_length=8, max_length=128)

class Login(StrictModel):
    username: str = Field(min_length=1, max_length=24)
    password: str = Field(min_length=1, max_length=128)

class RoomCreate(StrictModel):
    title: str = Field(min_length=1, max_length=60)
    preset: Literal['harbor', 'frontier', 'custom'] = 'harbor'
    premise: str = Field(default='', max_length=4000)
    ai_mode: Literal['demo', 'live'] = 'demo'

class JoinRoom(StrictModel):
    code: str = Field(min_length=6, max_length=6)

class Revision(StrictModel):
    expected_revision: int = Field(ge=0)
    request_key: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

class Action(Revision):
    text: str = Field(min_length=1, max_length=2000)
    character_id: str = Field(min_length=1, max_length=40)

class Chat(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    request_key: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

class FreeDice(Revision):
    expression: str = Field(min_length=3, max_length=16)

class Rollback(Revision):
    target_event_id: str = Field(min_length=1, max_length=40)
    reason: str = Field(default='房主回档', min_length=1, max_length=160)

class Assign(Revision):
    user_id: str | None = None

class Attributes(StrictModel):
    strength: int = Field(default=0, ge=-3, le=5)
    dexterity: int = Field(default=0, ge=-3, le=5)
    knowledge: int = Field(default=0, ge=-3, le=5)
    insight: int = Field(default=0, ge=-3, le=5)
    charisma: int = Field(default=0, ge=-3, le=5)

class CharacterInput(Revision):
    name: str = Field(min_length=1, max_length=32)
    archetype: str = Field(min_length=1, max_length=32)
    description: str = Field(default='', max_length=1000)
    avatar: Literal['feather', 'shield', 'sword', 'book', 'spark'] = 'feather'
    hp: int = Field(default=12, ge=0, le=100)
    max_hp: int = Field(default=12, ge=1, le=100)
    stress: int = Field(default=0, ge=0, le=6)
    attributes: Attributes = Field(default_factory=Attributes)
    inventory: list[str] = Field(default_factory=list, max_length=24)

    @field_validator('inventory')
    @classmethod
    def item_lengths(cls, value):
        if any(not item.strip() or len(item) > 60 for item in value):
            raise ValueError('每件物品需要1至60个字符')
        return [item.strip() for item in value]

    @model_validator(mode='after')
    def hp_range(self):
        if self.hp > self.max_hp:
            raise ValueError('当前生命不能超过生命上限')
        return self

class LoreEntry(StrictModel):
    id: str = Field(default='', max_length=40)
    title: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=1, max_length=3000)
    tags: str = Field(default='', max_length=120)

class WorldUpdate(Revision):
    title: str = Field(min_length=1, max_length=80)
    premise: str = Field(min_length=1, max_length=4000)
    tone: str = Field(default='克制、神秘、有选择的代价', max_length=160)
    lore: list[LoreEntry] = Field(default_factory=list, max_length=40)

class SettingsUpdate(Revision):
    ai_mode: Literal['demo', 'live']

class GMNote(Revision):
    text: str = Field(min_length=1, max_length=4000)
    scene_title: str = Field(default='', max_length=80)

class CheckProposal(StrictModel):
    attribute: Attribute
    dc: int = Field(ge=8, le=20)
    reason: str = Field(min_length=1, max_length=200)
    risk: Literal['none', 'harm', 'stress'] = 'none'

class Decision(StrictModel):
    narration: str = Field(min_length=1, max_length=4000)
    scene_title: str | None = Field(default=None, max_length=80)
    facts: list[str] = Field(default_factory=list, max_length=4)
    check: CheckProposal | None = None

    @field_validator('facts')
    @classmethod
    def facts_limits(cls, value):
        if any(len(item) > 200 or not item.strip() for item in value):
            raise ValueError('事实条目长度无效')
        return value
