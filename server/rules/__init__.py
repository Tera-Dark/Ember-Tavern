"""Reviewed rule adapters, separate from narrative hosts and content packages.

A new system requires server code, schemas, migrations and regression tests; a
worldbook cannot register executable rules or claim full D&D/CoC compatibility.
"""
from typing import Protocol

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


def engine_for(state=None):
    rule_id = (state or {}).get('world', {}).get('rule_system', 'ember-light/v1')
    if rule_id not in ENGINES:
        raise HTTPException(422, '该可执行规则系统尚未安装，不能只靠规则文本启用')
    return ENGINES[rule_id]
