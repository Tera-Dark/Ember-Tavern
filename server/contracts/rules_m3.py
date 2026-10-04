"""Bounded command contracts for the experimental M3 rule adapters."""
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .common import Contract


AbilityScore = Annotated[int, Field(ge=3, le=20)]
ResourceName = Literal['food', 'timber', 'stone', 'coin']
BuildingName = Literal['farm', 'sawmill', 'quarry', 'market']


class DndAbilityScores(Contract):
    strength: AbilityScore = 10
    dexterity: AbilityScore = 10
    constitution: AbilityScore = 10
    intelligence: AbilityScore = 10
    wisdom: AbilityScore = 10
    charisma: AbilityScore = 10


class Dnd5eSheet(Contract):
    """A minimal, public combat sheet; it contains no SRD prose or class features."""
    level: int = Field(default=1, ge=1, le=4)
    ability_scores: DndAbilityScores = Field(default_factory=DndAbilityScores)
    armor_class: int = Field(default=10, ge=5, le=30)
    weapon_die: Literal[4, 6, 8, 10, 12] = 6
    weapon_ability: Literal['strength', 'dexterity'] = 'strength'
    hit_die: Literal[6, 8, 10, 12] = 8
    # This slice does not infer HP from a class hit die; the host/GM pins it explicitly.
    max_hit_points: int | None = Field(default=None, ge=1, le=100)


class DndEncounterSetup(Contract):
    name: str = Field(min_length=1, max_length=80)
    hit_points: int = Field(ge=1, le=300)
    armor_class: int = Field(ge=5, le=30)
    initiative_bonus: int = Field(default=0, ge=-5, le=10)
    attack_bonus: int = Field(default=2, ge=-5, le=15)
    damage_die: Literal[4, 6, 8, 10, 12] = 6
    damage_bonus: int = Field(default=1, ge=-5, le=15)


class DndTurnAction(Contract):
    character_id: str = Field(min_length=1, max_length=40)
    action: Literal['attack', 'dodge']


class DndRest(Contract):
    character_id: str = Field(min_length=1, max_length=40)
    kind: Literal['short', 'long']


class StrategyOrder(Contract):
    """One cooperative order per member each planning turn."""
    action: Literal['build', 'repair', 'trade']
    building: BuildingName | None = None
    source: ResourceName | None = None
    destination: ResourceName | None = None
    amount: int = Field(default=2, ge=2, le=10)

    @model_validator(mode='after')
    def action_fields(self):
        if self.action == 'build':
            if self.building is None or self.source is not None or self.destination is not None:
                raise ValueError('建造订单需要且只能指定 building')
        elif self.action == 'repair':
            if self.building is not None or self.source is not None or self.destination is not None:
                raise ValueError('修复订单不接受 building 或 trade 字段')
        else:
            if self.building is not None or self.source is None or self.destination is None:
                raise ValueError('交易订单需要 source 和 destination')
            if self.source == self.destination:
                raise ValueError('交易的来源和目标资源必须不同')
            if self.amount % 2:
                raise ValueError('交易数量必须为偶数；每 2 单位来源资源兑换 1 单位目标资源')
        return self
