import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

ID = Annotated[str, Field(pattern=r'^[a-z][a-z0-9-]{2,47}$')]
VERSION = Annotated[str, Field(max_length=32, pattern=r'^[0-9]+\.[0-9]+\.[0-9]+$')]
RESOURCE = Annotated[str, Field(pattern=r'^[a-z][a-z0-9.-]{1,70}/v[1-9][0-9]*$')]


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, strict=True)


class Metadata(Contract):
    id: ID
    name: str = Field(min_length=1, max_length=80)
    version: VERSION = '1.0.0'
    description: str = Field(default='', max_length=2000)
    authors: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=12)
    license: str = Field(default='', max_length=80)
    tags: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=24)


class Extensible(Contract):
    # Vendor data must be namespaced; it cannot change permissions or run code.
    extensions: dict[RESOURCE, dict] = Field(default_factory=dict, max_length=16)

    @field_validator('extensions')
    @classmethod
    def bounded_extensions(cls, value):
        stack, nodes = [(value, 0)], 0
        while stack:
            child, depth = stack.pop()
            nodes += 1
            if depth > 12 or nodes > 20000:
                raise ValueError('扩展数据的嵌套不能超过 12 层，节点不能超过 20000')
            if isinstance(child, dict):
                stack.extend((item, depth + 1) for item in child.values())
            elif isinstance(child, list):
                stack.extend((item, depth + 1) for item in child)
        try:
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False).encode()
        except (ValueError, TypeError, RecursionError) as exc:
            raise ValueError('扩展字段必须是有限、标准 JSON 数据') from exc
        if len(encoded) > 32768:
            raise ValueError('扩展数据不能超过 32 KiB')
        return value
