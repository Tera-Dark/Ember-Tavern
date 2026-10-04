"""Original cooperative economy adapter with deterministic, auditable settlement."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from fastapi import HTTPException
from ..contracts.rules_m3 import StrategyOrder
from ..schemas import Decision
from .light import free_roll

RULE_ID = 'ember-coop-settlement/v1'
IMPLEMENTATION_VERSION = '0.1.0'
IMPLEMENTATION_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
RULE_TEXT = (
    '实验合作经营规则：共享食物、木材、石料、银币；成员每回合各提交一个建造、修复或交易订单，'
    '房主结算后统一应用资源消耗、建筑生产与服务器随机事件。目标为八回合内修复三段水道。'
    '叙事文本不能改写订单或资源；未支持的动作需房主文字裁决。'
)

BUILD_COSTS = {
    'farm': {'timber': 3, 'coin': 1},
    'sawmill': {'timber': 4, 'food': 2},
    'quarry': {'timber': 3, 'food': 2},
    'market': {'timber': 2, 'food': 1},
}
REPAIR_COST = {'timber': 4, 'stone': 4, 'food': 2}
PRODUCTION = {'farm': ('food', 2), 'sawmill': ('timber', 2),
              'quarry': ('stone', 2), 'market': ('coin', 1)}
RESOURCE_CAP = 1000
MAX_TURNS = 8
GOAL_REPAIRS = 3


def _roll(sides, randbelow):
    value = randbelow(sides)
    if type(value) is not int or not 0 <= value < sides:
        raise ValueError('规则随机源必须返回范围内的整数')
    return value + 1


def _active(state):
    rules = state.get('_rule_state')
    if not isinstance(rules, dict) or rules.get('adapter_id') != RULE_ID:
        raise HTTPException(409, '此房间的合作经营规则状态尚未初始化；请从对应玩法预设新建房间')
    return rules


def _zero_cost():
    return {'food': 0, 'timber': 0, 'stone': 0, 'coin': 0}


def _order_cost(order):
    cost = _zero_cost()
    if order['action'] == 'build':
        cost.update(BUILD_COSTS[order['building']])
    elif order['action'] == 'repair':
        cost.update(REPAIR_COST)
    elif order['action'] == 'trade':
        cost[order['source']] = order['amount']
    return cost


def _available(rules):
    available = dict(rules['resources'])
    for order in rules['orders']:
        for resource, amount in order['reserved_cost'].items():
            available[resource] -= amount
    return available


def _validate_affordable(rules, order):
    available = _available(rules)
    cost = _order_cost(order)
    missing = [name for name, amount in cost.items() if amount > available[name]]
    if missing:
        names = {'food': '食物', 'timber': '木材', 'stone': '石料', 'coin': '银币'}
        raise HTTPException(422, '资源不足，不能提交订单：' + '、'.join(names[name] for name in missing))
    if order['action'] == 'trade':
        already_planned = sum(item['amount'] // 2 for item in rules['orders']
                              if item['action'] == 'trade' and item['destination'] == order['destination'])
        if order['amount'] // 2 + already_planned > RESOURCE_CAP - rules['resources'][order['destination']]:
            raise HTTPException(422, '交易后资源会超过上限')
    if order['action'] == 'build':
        planned = sum(1 for item in rules['orders']
                      if item['action'] == 'build' and item['building'] == order['building'])
        if rules['buildings'][order['building']] + planned >= 3:
            raise HTTPException(422, '单类建筑最多三级')
    if order['action'] == 'repair':
        planned = sum(1 for item in rules['orders'] if item['action'] == 'repair')
        if rules['bridge_repairs'] + planned >= GOAL_REPAIRS:
            raise HTTPException(422, '水道已修复完成，不需要更多修复订单')


def _apply_cost(resources, cost):
    for resource, amount in cost.items():
        if amount:
            resources[resource] -= amount


def _finish_if_goal(rules):
    if rules['bridge_repairs'] >= GOAL_REPAIRS:
        rules['status'] = 'completed'
        rules['phase'] = 'completed'
    elif rules['turn'] > MAX_TURNS:
        rules['status'] = 'expired'
        rules['phase'] = 'completed'


class CooperativeSettlementRules:
    id = RULE_ID
    description = RULE_TEXT
    status = 'experimental'

    def roll(self, expression):
        return free_roll(expression)

    def resolve(self, state):
        raise HTTPException(422, '合作经营玩法没有余烬轻规则的待检定流程；请通过规则实验提交类型化订单')

    def validate_decision(self, state, value):
        decision = Decision.model_validate(value.model_dump() if isinstance(value, Decision) else value)
        if decision.check is not None:
            raise ValueError('合作经营玩法不支持 AI 创建轻规则检定；请通过行动订单或由房主裁决')
        return decision

    def initial_rule_state(self, state):
        return {
            'adapter_id': self.id,
            'status': 'active',
            'phase': 'planning',
            'turn': 1,
            'max_turns': MAX_TURNS,
            'goal': '修复三段水道，并在第八回合结算前完成。',
            'goal_repairs': GOAL_REPAIRS,
            'bridge_repairs': 0,
            'resources': {'food': 10, 'timber': 6, 'stone': 3, 'coin': 4},
            'buildings': {'farm': 1, 'sawmill': 1, 'quarry': 0, 'market': 0},
            'orders': [],
            'settlements': [],
        }

    def project_state(self, state):
        rules = deepcopy(_active(state))
        rules['available_resources'] = _available(rules)
        # Actor database IDs and reservation internals are implementation detail;
        # the cooperative board publishes display names and resolved costs only.
        for order in rules['orders']:
            order.pop('actor_id', None)
            order.pop('reserved_cost', None)
        rules['implementation_version'] = IMPLEMENTATION_VERSION
        rules['implementation_sha256'] = IMPLEMENTATION_SHA256
        return rules

    def plan_order(self, state, value, user, turn_members):
        rules = _active(state)
        if rules['status'] != 'active' or rules['phase'] != 'planning':
            raise HTTPException(409, '当前不是可提交订单的规划阶段')
        if any(item['actor_id'] == user['id'] for item in rules['orders']):
            raise HTTPException(409, '每位成员每回合只能提交一个订单')
        if len(rules['orders']) >= max(1, turn_members):
            raise HTTPException(409, '本回合所有成员均已提交；请由房主结算')
        order = StrategyOrder.model_validate(value).model_dump(mode='json')
        _validate_affordable(rules, order)
        cost = _order_cost(order)
        record = {'id': hashlib.sha256(
            f"{rules['turn']}:{user['id']}:{json.dumps(order, sort_keys=True)}".encode()).hexdigest()[:20],
                  'turn': rules['turn'], 'actor_id': user['id'],
                  'actor_name': user['display_name'], **order, 'reserved_cost': cost}
        rules['orders'].append(record)
        return {'text': f"{user['display_name']} 提交了第 {rules['turn']} 回合合作订单。",
                'payload': {'kind': 'strategy_order', 'turn': rules['turn'],
                            'actor_name': user['display_name'], 'action': order['action'],
                            'building': order['building'], 'source': order['source'],
                            'destination': order['destination'], 'amount': order['amount']}}

    def settle_turn(self, state, randbelow):
        rules = _active(state)
        if rules['status'] != 'active' or rules['phase'] != 'planning':
            raise HTTPException(409, '当前没有可结算的合作经营回合')
        if not rules['orders']:
            raise HTTPException(422, '至少需要一位成员提交订单后才能结算')
        # Resolve on a detached copy first. Any validation/settlement failure
        # leaves the room snapshot and all queued orders untouched.
        next_rules = deepcopy(rules)
        before = dict(next_rules['resources'])
        resolved = []
        random_event = None
        for order in next_rules['orders']:
            actual = _order_cost(order)
            if any(actual[name] > next_rules['resources'][name] for name in actual):
                raise HTTPException(409, '结算前资源已变化；本回合未写入，请保留订单并由房主核对')
            _apply_cost(next_rules['resources'], actual)
            if order['action'] == 'build':
                next_rules['buildings'][order['building']] += 1
                detail = f"建造 {order['building']}，消耗 {actual}"
            elif order['action'] == 'repair':
                next_rules['bridge_repairs'] += 1
                detail = f"修复水道 {next_rules['bridge_repairs']}/{GOAL_REPAIRS}，消耗 {actual}"
            else:
                received = order['amount'] // 2
                next_rules['resources'][order['destination']] += received
                detail = (f"交易 {order['amount']} {order['source']} → "
                          f"{received} {order['destination']}")
            resolved.append({'id': order['id'], 'actor_name': order['actor_name'],
                             'action': order['action'], 'detail': detail})
        _finish_if_goal(next_rules)
        production = {resource: 0 for resource in next_rules['resources']}
        if next_rules['status'] == 'active':
            for building, (resource, each) in PRODUCTION.items():
                produced = next_rules['buildings'][building] * each
                before_production = next_rules['resources'][resource]
                next_rules['resources'][resource] = min(RESOURCE_CAP,
                                                         before_production + produced)
                production[resource] += next_rules['resources'][resource] - before_production
            event_roll = _roll(6, randbelow)
            random_event = {'roll': event_roll, 'name': '平安无事', 'changes': {}}
            events = {
                1: ('风暴损坏木料', {'timber': -2}),
                2: ('干旱消耗口粮', {'food': -2}),
                3: ('沿途商队补给', {'coin': 1}),
            }
            if event_roll in events:
                label, requested_changes = events[event_roll]
                changes = {}
                for resource, delta in requested_changes.items():
                    before_event = next_rules['resources'][resource]
                    after_event = max(0, min(RESOURCE_CAP, before_event + delta))
                    next_rules['resources'][resource] = after_event
                    changes[resource] = after_event - before_event
                random_event = {'roll': event_roll, 'name': label, 'changes': changes}
            next_rules['turn'] += 1
            _finish_if_goal(next_rules)
        next_rules['orders'] = []
        result = {'turn_resolved': rules['turn'], 'orders': resolved,
                  'production': production, 'random_event': random_event,
                  'resources_before': before, 'resources_after': dict(next_rules['resources']),
                  'bridge_repairs': next_rules['bridge_repairs'], 'status': next_rules['status'],
                  'next_turn': next_rules['turn'] if next_rules['status'] == 'active' else None}
        next_rules['settlements'].append(result)
        next_rules['settlements'] = next_rules['settlements'][-8:]
        state['_rule_state'] = next_rules
        names = '；'.join(item['actor_name'] + '：' + item['detail'] for item in resolved)
        event_text = (f"第 {result['turn_resolved']} 回合结算完成。{names}。"
                      f"资源：食物 {next_rules['resources']['food']}、木材 {next_rules['resources']['timber']}、"
                      f"石料 {next_rules['resources']['stone']}、银币 {next_rules['resources']['coin']}。"
                      f"{random_event['name'] if random_event else '本次达成目标，不再结算生产。'}")
        return {'text': event_text, 'payload': {'kind': 'strategy_settlement', **result}}

    def contract(self):
        return {
            'id': self.id, 'implementation_version': IMPLEMENTATION_VERSION,
            'implementation_sha256': IMPLEMENTATION_SHA256, 'name': '余烬边境合作经营实验',
            'description': self.description, 'status': self.status,
            'scope': ['共享资源', '每成员每回合一个订单', '建造', '修复', '交易',
                      '生产', '有界随机事件', '八回合目标'],
            'not_supported': ['PvP', '私人视野', '外交战斗', '多城管理', '队列', '市场价格波动', '自由脚本'],
            'dice': {'max_count': 20, 'min_sides': 2, 'max_sides': 100, 'max_modifier': 100},
            'order_schema': StrategyOrder.model_json_schema(),
            'check_schema': Decision.model_json_schema(),
        }
