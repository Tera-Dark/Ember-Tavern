"""Versioned, data-only index contract for the local/community work registry."""
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from .common import Contract, ID, RESOURCE, VERSION

SHA256 = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
HostVersion = Annotated[str, Field(pattern=r'^[0-9]+[.][0-9]+[.][0-9]+(?:-[0-9A-Za-z.-]+)?$')]
HTTPS_URL = Annotated[str, Field(min_length=9, max_length=2048, pattern=r'^https://[^\s]+$')]
RegistryStatus = Literal[
    'example', 'source-template-not-published', 'legacy-reference-only',
    'community-submitted', 'community-playtested', 'official-recommended',
    'incompatible', 'archived', 'original-playtest-example',
    'experimental-playable-vertical-sample',
]
MAINTENANCE = Literal['active', 'maintenance-needed', 'unmaintained', 'unknown', 'archived']


def _safe_relative_path(value):
    if not value:
        return value
    parts = value.replace('\\', '/').split('/')
    if (not value.isascii() or value != value.lower() or value.startswith('/')
            or '\\' in value or any(part in ('', '.', '..') or ':' in part for part in parts)):
        raise ValueError('registry 路径必须是规范的小写 ASCII 相对路径，不得包含链接、盘符、空段或 ..')
    if any(part.startswith('.') for part in parts):
        raise ValueError('registry 路径不接受隐藏段')
    return value


RelativePath = Annotated[str, Field(min_length=1, max_length=180)]


class PluginRegistryEntry(Contract):
    id: ID
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default='', max_length=1000)
    category: str = Field(default='扩展', min_length=1, max_length=64)
    version: VERSION
    package: RelativePath | None = Field(default=None, description='相对于仓库 plugin-packages/ 的发行 ZIP 路径')
    sha256: SHA256 | None = Field(default=None, description='本地发行 ZIP 的 SHA-256；不会通过网络下载 URL 来复核')
    download_url: HTTPS_URL | None = Field(default=None, description='公开下载地址；目录 CI 不访问或验证在线可用性')
    backend: bool
    api_version: Literal[1]
    review_status: RegistryStatus
    capabilities: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=24)
    requires: list[ID] = Field(default_factory=list, max_length=40)
    uses: list[RESOURCE] = Field(default_factory=list, max_length=24)
    provides: list[RESOURCE] = Field(default_factory=list, max_length=24)
    minimum_host: VERSION
    template_path: RelativePath
    license: str = Field(default='UNLICENSED', min_length=1, max_length=80)
    authors: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=12)
    source_url: HTTPS_URL | None = None
    maintenance_status: MAINTENANCE = 'unknown'
    issue_url: HTTPS_URL | None = None
    download_note: str | None = Field(default=None, max_length=500)
    evidence: list[HTTPS_URL] = Field(default_factory=list, max_length=12)

    @field_validator('package', 'template_path')
    @classmethod
    def paths_are_safe(cls, value):
        return _safe_relative_path(value)

    @model_validator(mode='after')
    def release_and_review_integrity(self):
        for values in (self.capabilities, self.requires, self.uses, self.provides):
            if len(values) != len(set(values)):
                raise ValueError('插件目录能力、依赖与资源声明不能重复')
        if self.id in self.requires:
            raise ValueError('插件不能依赖自己')
        if any(resource.startswith('core.') for resource in self.provides):
            raise ValueError('插件目录不能声明覆盖 core.* 宿主资源')
        if (self.package is None) != (self.sha256 is None):
            raise ValueError('本地插件包路径与 SHA256 必须同时提供或同时留空')
        if self.download_url and (self.package is None or self.sha256 is None):
            raise ValueError('有下载链接的插件必须锁定可核验的包路径与 SHA256')
        if self.review_status == 'source-template-not-published' and self.download_url:
            raise ValueError('仅源码模板不能声明为已发行下载')
        if self.download_url and self.license.strip().upper() == 'UNLICENSED' and self.review_status != 'legacy-reference-only':
            raise ValueError('除明确标记的历史引用外，未获许可的插件不能提供公开下载')
        if self.review_status in ('community-submitted', 'community-playtested', 'official-recommended'):
            if not self.authors or self.license.strip().upper() in ('', 'UNLICENSED'):
                raise ValueError('社区投稿／试玩／官方推荐必须标注作者与明确许可')
            if not (self.source_url or self.issue_url):
                raise ValueError('社区作品必须提供公开源码或维护联系入口')
        if self.review_status in ('community-playtested', 'official-recommended') and not self.evidence:
            raise ValueError('社区试玩／官方推荐必须提供可审阅证据链接')
        return self


class ContentTemplate(Contract):
    kind: Literal['worldbook', 'character', 'theme']
    format: str = Field(min_length=1, max_length=80)
    template_path: RelativePath
    schema_path: RelativePath

    @field_validator('template_path', 'schema_path')
    @classmethod
    def paths_are_safe(cls, value):
        return _safe_relative_path(value)


class GameplayTemplate(Contract):
    kind: Literal['preset', 'scenario']
    format: str = Field(min_length=1, max_length=80)
    template_path: RelativePath
    schema_path: RelativePath

    @field_validator('template_path', 'schema_path')
    @classmethod
    def paths_are_safe(cls, value):
        return _safe_relative_path(value)


class RegistryPluginPin(Contract):
    id: ID
    version: VERSION
    sha256: SHA256
    required: bool = True
    enabled: bool = True

    @model_validator(mode='after')
    def required_is_enabled(self):
        if self.required and not self.enabled:
            raise ValueError('目录中的必需模块必须启用')
        return self


class PresetRegistryEntry(Contract):
    id: ID
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default='', max_length=2000)
    tags: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=24)
    version: VERSION
    package_hash: SHA256
    source_path: RelativePath
    status: RegistryStatus
    download_url: HTTPS_URL | None = Field(default=None, description='公开预设归档地址；目录 CI 不联网验证')
    archive_sha256: SHA256 | None = Field(default=None, description='发布者声明的归档 SHA-256；当前目录校验不会下载归档')
    license: str = Field(min_length=1, max_length=80)
    authors: list[Annotated[str, Field(min_length=1, max_length=80)]] = Field(default_factory=list, max_length=12)
    rule_system: Annotated[str, Field(pattern=r'^[a-z][a-z0-9.-]{1,50}/v[1-9][0-9]*$')]
    rule_version: VERSION
    minimum_host: VERSION
    plugin_api: Literal[1] = 1
    language: str = Field(default='zh-CN', min_length=2, max_length=32)
    play_mode: Literal['investigation', 'adventure', 'slice-of-life']
    min_players: int = Field(ge=1, le=12)
    max_players: int = Field(ge=1, le=12)
    duration_minutes: int = Field(ge=10, le=600)
    difficulty: Literal['beginner', 'standard']
    content_warnings: list[Annotated[str, Field(min_length=1, max_length=120)]] = Field(default_factory=list, max_length=12)
    plugins: list[RegistryPluginPin] = Field(default_factory=list, max_length=24)
    source_url: HTTPS_URL | None = None
    maintenance_status: MAINTENANCE = 'unknown'
    issue_url: HTTPS_URL | None = None
    evidence: list[HTTPS_URL] = Field(default_factory=list, max_length=12)

    @field_validator('source_path')
    @classmethod
    def source_is_safe(cls, value):
        return _safe_relative_path(value)

    @model_validator(mode='after')
    def release_and_review_integrity(self):
        if self.min_players > self.max_players:
            raise ValueError('建议人数范围无效')
        if len({pin.id for pin in self.plugins}) != len(self.plugins):
            raise ValueError('预设锁定模块不能重复')
        if (self.download_url is None) != (self.archive_sha256 is None):
            raise ValueError('预设下载 URL 与归档 SHA256 必须同时提供或同时留空')
        if self.download_url and self.license.strip().upper() in ('', 'UNLICENSED'):
            raise ValueError('UNLICENSED／未声明许可的作品不能加入公开下载目录')
        if self.status in ('community-submitted', 'community-playtested', 'official-recommended'):
            if not self.authors or self.license.strip().upper() in ('', 'UNLICENSED'):
                raise ValueError('社区投稿／试玩／官方推荐必须标注作者与明确许可')
            if not (self.source_url or self.issue_url):
                raise ValueError('社区作品必须提供公开源码或维护联系入口')
        if self.status in ('community-playtested', 'official-recommended') and not self.evidence:
            raise ValueError('社区试玩／官方推荐必须提供可审阅证据链接')
        return self


class CoreSchemaEntry(Contract):
    kind: Annotated[str, Field(pattern=r'^[a-z][a-z0-9-]{1,47}$')]
    schema_path: RelativePath
    rule_system: str | None = Field(default=None, max_length=80)

    @field_validator('schema_path')
    @classmethod
    def schema_path_is_safe(cls, value):
        return _safe_relative_path(value)


class RegistryIndex(Contract):
    """Repository-local discovery index; never installs packages or code."""
    registry_version: Literal[1]
    plugin_api_version: Literal[1]
    github_repository: HTTPS_URL
    status: Literal['local-foundation-catalog', 'community-catalog']
    plugins: list[PluginRegistryEntry] = Field(default_factory=list, max_length=256)
    host_version: HostVersion = Field(max_length=40)
    content_templates: list[ContentTemplate] = Field(default_factory=list, max_length=16)
    scaffold_kinds: list[Annotated[str, Field(min_length=1, max_length=40)]] = Field(default_factory=list, max_length=32)
    gameplay_templates: list[GameplayTemplate] = Field(default_factory=list, max_length=16)
    preset_library: list[PresetRegistryEntry] = Field(default_factory=list, max_length=512)
    core_schemas: list[CoreSchemaEntry] = Field(default_factory=list, max_length=64)

    @model_validator(mode='after')
    def unique_catalog_identities(self):
        if len({(item.id, item.version) for item in self.plugins}) != len(self.plugins):
            raise ValueError('插件 registry ID／版本不能重复')
        if len({(item.id, item.version) for item in self.preset_library}) != len(self.preset_library):
            raise ValueError('预设 registry ID／版本不能重复')
        if len({item.kind for item in self.content_templates}) != len(self.content_templates):
            raise ValueError('内容模板类型不能重复')
        if len({item.kind for item in self.gameplay_templates}) != len(self.gameplay_templates):
            raise ValueError('玩法模板类型不能重复')
        if len({item.kind for item in self.core_schemas}) != len(self.core_schemas):
            raise ValueError('核心 Schema 类型不能重复')
        return self
