from typing import Literal
from pydantic import Field, field_validator
from .contracts.common import Contract
from .contracts.content import Attributes, CharacterData, LoreEntry, WorldData
from .contracts.campaign_state import CampaignState
from .contracts.rules_m3 import Dnd5eSheet, DndEncounterSetup, DndTurnAction, DndRest, StrategyOrder
import re

Attribute = Literal['strength', 'dexterity', 'knowledge', 'insight', 'charisma']

class StrictModel(Contract):
    pass

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
    ai_mode: Literal['demo', 'single', 'live'] = 'demo'
    request_key: str | None = Field(default=None, min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

class JoinRoom(StrictModel):
    code: str = Field(min_length=6, max_length=6)

class Revision(StrictModel):
    expected_revision: int = Field(ge=0)
    request_key: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

class Action(Revision):
    text: str = Field(min_length=1, max_length=2000)
    character_id: str = Field(min_length=1, max_length=40)
    # Required by the new collection mode; optional for existing free-action clients.
    branch: int | None = Field(default=None, ge=1)

class BranchRevision(Revision):
    branch: int = Field(ge=1)

class CampaignStateUpdate(BranchRevision):
    ledger: CampaignState

class ActionModeUpdate(BranchRevision):
    mode: Literal['free', 'round']

class ActionRoundSettle(BranchRevision):
    pass

class MemorySummaryUpdate(BranchRevision):
    text: str = Field(default='', max_length=4000)
    source_event_ids: list[str] = Field(default_factory=list, max_length=50)

class DndSheetUpdate(BranchRevision, Dnd5eSheet):
    pass

class DndEncounterStart(BranchRevision, DndEncounterSetup):
    pass

class DndActionRequest(BranchRevision, DndTurnAction):
    pass

class DndRestRequest(BranchRevision, DndRest):
    pass

class StrategyOrderRequest(BranchRevision, StrategyOrder):
    pass

class StrategySettleRequest(BranchRevision):
    pass

class Chat(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    request_key: str = Field(min_length=8, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')

class FreeDice(Revision):
    expression: str = Field(min_length=3, max_length=16)
    source_plugin: str | None = Field(default=None, pattern=r'^[a-z][a-z0-9-]{2,47}$')

class Rollback(Revision):
    target_event_id: str = Field(min_length=1, max_length=40)
    reason: str = Field(default='房主回档', min_length=1, max_length=160)

class Assign(Revision):
    user_id: str | None = None

class CharacterInput(Revision, CharacterData):
    pass

class WorldUpdate(Revision, WorldData):
    pass

class SettingsUpdate(Revision):
    ai_mode: Literal['demo', 'single', 'live']

class GMNote(Revision):
    text: str = Field(min_length=1, max_length=4000)
    scene_title: str = Field(default='', max_length=80)

class CheckProposal(StrictModel):
    attribute: Attribute
    dc: int = Field(ge=8, le=20)
    reason: str = Field(min_length=1, max_length=200)
    risk: Literal['none', 'harm', 'stress'] = 'none'
    # Used only when a collected team round contains more than one actor.
    character_id: str | None = Field(default=None, min_length=1, max_length=40)

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
