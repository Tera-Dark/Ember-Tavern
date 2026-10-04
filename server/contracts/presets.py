"""Data-only gameplay compositions and finite scenario graphs. No executable DSL."""
from typing import Annotated, Literal
from pydantic import Field, model_validator
from .common import Contract, Metadata, ID, VERSION
from .content import RULE_SYSTEM

SHA256 = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
LOCAL_ID = Annotated[str, Field(pattern=r'^[a-z][a-z0-9-]{0,47}$')]
PATH = Annotated[str, Field(min_length=1, max_length=160)]
MAX_SCENARIO_BYTES = 128 * 1024


class Component(Contract):
    path: PATH
    id: ID
    version: VERSION
    sha256: SHA256


class DocumentFile(Contract):
    path: PATH
    sha256: SHA256


class PluginPin(Contract):
    id: ID
    version: VERSION
    sha256: SHA256
    required: bool = True
    enabled: bool = True

    @model_validator(mode='after')
    def required_is_enabled(self):
        if self.required and not self.enabled:
            raise ValueError('必需模块必须启用；预设不能用关闭模块的配置假装满足依赖')
        return self


class NarrativeProfile(Contract):
    style: str = Field(default='尊重玩家选择，提供可继续行动的叙事。', max_length=240)
    checks: Literal['normal', 'narrative'] = 'normal'


class Preset(Contract):
    format: Literal['ember.preset/v1']
    metadata: Metadata
    minimum_host: VERSION = '2.4.0'
    plugin_api: Literal[1] = 1
    language: str = Field(default='zh-CN', max_length=32)
    play_mode: Literal['investigation', 'adventure', 'slice-of-life']
    min_players: int = Field(default=1, ge=1, le=12)
    max_players: int = Field(default=4, ge=1, le=12)
    duration_minutes: int = Field(default=60, ge=10, le=600)
    difficulty: Literal['beginner', 'standard'] = 'beginner'
    content_warnings: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=12)
    rule_system: RULE_SYSTEM = 'ember-light/v1'
    rule_version: VERSION = '1.1.0'
    profile: NarrativeProfile = Field(default_factory=NarrativeProfile)
    worldbook: Component
    scenario: Component
    characters: list[Component] = Field(min_length=1, max_length=12)
    theme: Component | None = None
    plugins: list[PluginPin] = Field(default_factory=list, max_length=24)
    documents: list[DocumentFile] = Field(default_factory=list, max_length=12)

    @model_validator(mode='after')
    def unique_components(self):
        if self.min_players > self.max_players:
            raise ValueError('建议人数范围无效')
        refs = [self.worldbook, self.scenario, *self.characters, *([self.theme] if self.theme else []), *self.documents]
        paths = [ref.path for ref in refs]
        if len(paths) != len(set(paths)) or 'preset.json' in paths:
            raise ValueError('组件路径不能重复，也不能引用 preset.json 自身')
        char_ids = [ref.id for ref in self.characters]
        if len(set(char_ids)) != len(char_ids):
            raise ValueError('角色模板 ID 不能重复')
        pids = [ref.id for ref in self.plugins]
        if len(set(pids)) != len(pids):
            raise ValueError('模块 ID 不能重复')
        return self


class Clue(Contract):
    id: LOCAL_ID
    title: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=1500)
    gm_notes: str = Field(default='', max_length=1500)


class Transition(Contract):
    id: LOCAL_ID
    label: str = Field(min_length=1, max_length=120)
    target: LOCAL_ID
    requires_clues: list[LOCAL_ID] = Field(default_factory=list, max_length=12)
    requires_rule_status: Literal['completed', 'expired', 'victory', 'defeat', 'retreated'] | None = None
    gm_guidance: str = Field(default='', max_length=1500)


class Scene(Contract):
    id: LOCAL_ID
    title: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=3000)
    gm_notes: str = Field(default='', max_length=3000)
    kind: Literal['scene', 'ending'] = 'scene'
    clues: list[LOCAL_ID] = Field(default_factory=list, max_length=24)
    transitions: list[Transition] = Field(default_factory=list, max_length=12)


class Scenario(Contract):
    format: Literal['ember.scenario/v1']
    metadata: Metadata
    rule_system: RULE_SYSTEM = 'ember-light/v1'
    objective: str = Field(min_length=1, max_length=1000)
    start_scene: LOCAL_ID
    scenes: list[Scene] = Field(min_length=2, max_length=32)
    clues: list[Clue] = Field(default_factory=list, max_length=48)

    @model_validator(mode='after')
    def graph_integrity(self):
        import json
        scenes = {scene.id: scene for scene in self.scenes}
        clues = {clue.id: clue for clue in self.clues}
        if len(scenes) != len(self.scenes) or len(clues) != len(self.clues):
            raise ValueError('场景 / 线索 ID 不能重复')
        if self.start_scene not in scenes or scenes[self.start_scene].kind != 'scene':
            raise ValueError('开场必须引用一个普通场景')
        for scene in self.scenes:
            if len(set(scene.clues)) != len(scene.clues) or any(cid not in clues for cid in scene.clues):
                raise ValueError('场景线索引用无效或重复')
            edges = [edge.id for edge in scene.transitions]
            if len(edges) != len(set(edges)):
                raise ValueError('同场景推进选项 ID 不能重复')
            if scene.kind == 'ending' and scene.transitions:
                raise ValueError('结局不能继续自动推进；需要重开或回档')
            if scene.kind == 'scene' and not scene.transitions:
                raise ValueError('普通场景至少需要一种继续路线')
            for edge in scene.transitions:
                if edge.target not in scenes or any(cid not in clues for cid in edge.requires_clues):
                    raise ValueError('推进路线引用了不存在的场景或线索')
                if len(edge.requires_clues) != len(set(edge.requires_clues)):
                    raise ValueError('线索前置条件不能重复')
        reachable, pending = set(), [self.start_scene]
        while pending:
            sid = pending.pop()
            if sid in reachable:
                continue
            reachable.add(sid)
            pending.extend(edge.target for edge in scenes[sid].transitions)
        if reachable != set(scenes) or not any(scenes[sid].kind == 'ending' for sid in reachable):
            raise ValueError('所有场景必须从开场可达，并至少存在一个结局')
        possible_scenes, possible_clues = {self.start_scene}, set()
        while True:
            before = (len(possible_scenes), len(possible_clues))
            for sid in list(possible_scenes):
                possible_clues.update(scenes[sid].clues)
                possible_scenes.update(edge.target for edge in scenes[sid].transitions if set(edge.requires_clues) <= possible_clues)
            if before == (len(possible_scenes), len(possible_clues)): break
        if possible_scenes != set(scenes):
            raise ValueError('线索前置条件造成不可达场景；不能只通过无条件图校验')
        supplied = {cid for scene in self.scenes for cid in scene.clues}
        if supplied != set(clues):
            raise ValueError('每条线索必须在某个场景有可揭示入口')
        if len(json.dumps(self.model_dump(mode='json'), ensure_ascii=False, separators=(',', ':')).encode()) > MAX_SCENARIO_BYTES:
            raise ValueError('剧本不能超过 128 KiB')
        return self


PRESET_MODELS = {'preset': Preset, 'scenario': Scenario}
