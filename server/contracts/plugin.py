"""Single manifest validator used by discovery, packaging, installation and CI."""
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .common import Contract, ID, RESOURCE, VERSION

OPERATION = Annotated[str, Field(pattern=r'^[a-z][a-z0-9_-]{0,47}$')]
CAPABILITY = Annotated[str, Field(min_length=1, max_length=120, pattern=r'^[a-z][a-z0-9:./_-]*$')]


class UI(Contract):
    group: str = Field(min_length=1, max_length=48, pattern=r'^[a-z][a-z0-9-]*$')
    label: str = Field(default='', max_length=80)
    slot: Literal['toolbar', 'main']
    height: int = Field(default=500, ge=120, le=1200, strict=True)


class Manifest(Contract):
    id: ID
    name: str = Field(min_length=1, max_length=80)
    version: VERSION
    description: str = Field(min_length=1, max_length=1000)
    authors: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=12)
    license: str = Field(default='', max_length=80)
    homepage: Annotated[str, Field(max_length=400, pattern=r'^https://[^\s]+$')] | None = None
    minimum_host: VERSION = '2.1.0'
    api_version: int = Field(ge=1, strict=True)
    state_version: int = Field(default=1, ge=1, strict=True)
    default_enabled: bool = Field(default=False, strict=True)
    backend: Literal['backend.py'] | None = None
    frontend: Literal['ui.js'] | None = None
    category: str = Field(default='扩展', max_length=64)
    icon: str = Field(default='puzzle', max_length=64)
    requires: list[ID] = Field(default_factory=list, max_length=40)
    uses: list[RESOURCE] = Field(default_factory=list, max_length=40)
    provides: list[RESOURCE] = Field(default_factory=list, max_length=40)
    capabilities: list[CAPABILITY] = Field(default_factory=list, max_length=40)
    actions: list[OPERATION] = Field(default_factory=list, max_length=40)
    signals: list[OPERATION] = Field(default_factory=list, max_length=40)
    hooks: list[Literal['gm']] = Field(default_factory=list, max_length=1)
    ui: UI | None = None

    @field_validator('requires', 'uses', 'provides', 'capabilities', 'actions', 'signals', 'hooks')
    @classmethod
    def unique_names(cls, value):
        if len(value) != len(set(value)):
            raise ValueError('清单列表中不能有重复值')
        return value

    @model_validator(mode='after')
    def valid_declarations(self):
        if self.id in self.requires:
            raise ValueError('插件不能依赖自己')
        if (self.provides or self.hooks or self.actions or self.signals) and not self.backend:
            raise ValueError('资源、主持钩子、操作和信号需要后端入口')
        if self.ui and not self.frontend:
            raise ValueError('UI 插槽需要前端入口')
        if any(resource.startswith('core.') for resource in self.provides):
            raise ValueError('core.* 资源保留给宿主，插件不能覆盖')
        if 'gm' in self.hooks and 'model:gm' not in self.capabilities:
            raise ValueError('主持钩子必须声明 model:gm 能力')
        return self


def validate_manifest(document, folder: Path | None = None):
    manifest = Manifest.model_validate(document)
    if folder is not None:
        for entry in (manifest.backend, manifest.frontend):
            if entry and (not (folder / entry).is_file() or (folder / entry).is_symlink()):
                raise ValueError(f'缺少合法入口文件：{entry}')
    return manifest.model_dump(mode='json', exclude_none=True)


def needs_capability_grant(manifest):
    """Private reads, as well as effects, require explicit operator review."""
    return any(cap not in {'read:room', 'read:events'} for cap in manifest.get('capabilities', []))
