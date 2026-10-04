"""Reviewed host rule adapters. Python code registration is source-reviewed only.

Plugins and content packages cannot register adapters or replace core.* resources.
"""
from typing import Protocol
import hashlib
import json
import re

from fastapi import HTTPException
from .light import LightRules
from .dnd5e import Dnd5eRules
from .cooperative import CooperativeSettlementRules

RULE_ADAPTER_API_VERSION = 1


class RuleEngine(Protocol):
    id: str
    description: str

    def roll(self, expression: str) -> dict: ...
    def resolve(self, state: dict) -> dict: ...
    def validate_decision(self, state: dict, value): ...
    def contract(self) -> dict: ...


# Only adapters named here are executable. New entries require reviewed host
# code, a versioned contract, state migration, and deterministic test fixtures.
ENGINES: dict[str, RuleEngine] = {
    'ember-light/v1': LightRules(),
    'dnd5e-srd-5.2.1/v1': Dnd5eRules(),
    'ember-coop-settlement/v1': CooperativeSettlementRules(),
}


def contract_hash(engine):
    return hashlib.sha256(json.dumps(engine.contract(), ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def validate_registry():
    for identity, engine in ENGINES.items():
        contract = engine.contract()
        if identity != engine.id or contract.get('id') != identity:
            raise RuntimeError('Rule adapter identity does not match the reviewed registry.')
        if not re.fullmatch(r'[a-z][a-z0-9.-]{1,50}/v[1-9][0-9]*', identity):
            raise RuntimeError('Rule adapter identity is invalid.')
        if not isinstance(contract.get('implementation_version'), str) or not contract.get('implementation_version'):
            raise RuntimeError('Rule adapter implementation version is missing.')
        if not re.fullmatch(r'[a-f0-9]{64}', contract.get('implementation_sha256', '')):
            raise RuntimeError('Rule adapter must pin its implementation digest.')
        if not isinstance(contract.get('check_schema'), dict):
            raise RuntimeError('Rule adapter must publish a structured check/decision schema.')


def adapter_catalog():
    validate_registry()
    return {'api_version': RULE_ADAPTER_API_VERSION,
            'registration': 'reviewed-host-code-only',
            'notice': '内容包和第三方插件不能安装或覆盖规则适配器；SHA256 不等于代码审计。',
            'adapters': [
                {'id': identity, 'api_version': RULE_ADAPTER_API_VERSION,
                 'implementation_version': engine.contract()['implementation_version'],
                 'implementation_sha256': engine.contract()['implementation_sha256'],
                 'contract_sha256': contract_hash(engine), 'name': engine.contract().get('name', identity),
                 'description': engine.description, 'source': 'host-bundled',
                 'status': engine.contract().get('status', 'implemented'),
                 'scope': engine.contract().get('scope', []),
                 'not_supported': engine.contract().get('not_supported', [])}
                for identity, engine in sorted(ENGINES.items())]}


def engine_for(state=None):
    validate_registry()
    rule_id = (state or {}).get('world', {}).get('rule_system', 'ember-light/v1')
    if rule_id not in ENGINES:
        raise HTTPException(422, '该可执行规则系统尚未安装，不能只靠规则文本启用')
    engine = ENGINES[rule_id]
    pin = (state or {}).get('_preset_lock', {}).get('rule')
    if pin and (pin['id'] != engine.id or pin['contract_sha256'] != contract_hash(engine)):
        raise HTTPException(409, '原房间规则实现 / 契约已变化；恢复匹配版本后再结算，不会自动替换规则')
    return engine
