"""Reviewed rule adapters, separate from narrative hosts and content packages.

A new system requires server code, schemas, migrations and regression tests; a
worldbook cannot register executable rules or claim full D&D/CoC compatibility.
"""
from typing import Protocol
import hashlib
import json

from fastapi import HTTPException
from .light import LightRules


class RuleEngine(Protocol):
    id: str
    description: str

    def roll(self, expression: str) -> dict: ...
    def resolve(self, state: dict) -> dict: ...
    def validate_decision(self, state: dict, value): ...
    def contract(self) -> dict: ...


ENGINES: dict[str, RuleEngine] = {'ember-light/v1': LightRules()}


def contract_hash(engine):
    return hashlib.sha256(json.dumps(engine.contract(),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def engine_for(state=None):
    rule_id = (state or {}).get('world', {}).get('rule_system', 'ember-light/v1')
    if rule_id not in ENGINES:
        raise HTTPException(422, '该可执行规则系统尚未安装，不能只靠规则文本启用')
    engine = ENGINES[rule_id]
    pin = (state or {}).get('_preset_lock',{}).get('rule')
    if pin and (pin['id'] != engine.id or pin['contract_sha256'] != contract_hash(engine)):
        raise HTTPException(409, '原房间规则实现 / 契约已变化；恢复匹配版本后再结算，不会自动替换规则')
    return engine
