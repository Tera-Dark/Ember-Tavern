"""Data contracts for submissions, publisher provenance and maintainer decisions."""
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator, field_validator
from .common import Contract, ID, VERSION
from .registry import PluginRegistryEntry, PresetRegistryEntry, SHA256

COMMIT=r'^[a-f0-9]{40}$'
NAME=r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,99}$'


def github_repository(value):
    u=urlsplit(value)
    parts=u.path.strip('/').split('/')
    if (u.scheme!='https' or u.netloc!='github.com' or u.query or u.fragment
            or len(parts)!=2 or any(not re.fullmatch(NAME,p) or p in ('.','..') for p in parts)
            or u.path!='/'+('/'.join(parts))):
        raise ValueError('来源仓库必须是规范的 GitHub HTTPS 仓库地址')
    return value


def release_url(repository,tag,name):
    return f'{github_repository(repository)}/releases/download/{tag}/{name}'


class CommunityRelease(Contract):
    format: Literal['ember.community-release/v1']='ember.community-release/v1'
    kind: Literal['plugin','preset']
    id: ID
    version: VERSION
    repository: str=Field(max_length=240)
    source_commit: str=Field(pattern=COMMIT)
    sdk_commit: str=Field(pattern=COMMIT)
    tag: str=Field(min_length=1,max_length=100)
    archive_name: str=Field(pattern=r'^[a-z0-9][a-z0-9_.-]{0,99}\.zip$')
    archive_sha256: SHA256
    archive_bytes: int=Field(gt=0,le=8*1024*1024)
    package_hash: SHA256=Field(description='预设内容锁；插件为规范归档路径 / 字节的审计指纹，不授予运行时信任')
    @field_validator('repository')
    @classmethod
    def repository_is_canonical(cls,value):return github_repository(value)
    @model_validator(mode='after')
    def tag_is_exact(self):
        if self.tag!=f'{self.kind}-{self.id}-v{self.version}':raise ValueError('发行 tag 与作品身份 / 版本不符')
        return self


class RegistrySubmission(Contract):
    format: Literal['ember.registry-submission/v1']='ember.registry-submission/v1'
    kind: Literal['plugin','preset']
    entry: PluginRegistryEntry | PresetRegistryEntry
    release: CommunityRelease
    provenance_url: str=Field(max_length=2048)
    @model_validator(mode='after')
    def entry_and_release_are_locked(self):
        p=self.release;e=self.entry
        if self.kind!=p.kind or (e.id,e.version)!=(p.id,p.version):raise ValueError('投稿、目录项与发行身份不一致')
        if self.provenance_url!=release_url(p.repository,p.tag,'release-provenance.json'):raise ValueError('provenance URL 必须指向同一发行')
        if e.source_url!=f'{p.repository}/tree/{p.source_commit}':raise ValueError('源码 URL 必须锁定同一仓库的精确提交')
        if e.download_url!=release_url(p.repository,p.tag,p.archive_name):raise ValueError('下载 URL 必须锁定同一发行和归档')
        if isinstance(e,PluginRegistryEntry):
            if self.kind!='plugin' or e.review_status!='community-submitted' or e.sha256!=p.archive_sha256:
                raise ValueError('插件投稿只能申请 community-submitted，且归档散列必须一致')
            if e.template_path!=f'templates/community/{e.id}/{e.version}' or e.package!=f'{e.id}-{e.version}.zip':raise ValueError('插件投稿暂存路径不规范')
        else:
            if self.kind!='preset' or e.status!='community-submitted' or e.archive_sha256!=p.archive_sha256 or e.package_hash!=p.package_hash:
                raise ValueError('预设投稿只能申请 community-submitted，且内容 / 归档散列必须一致')
            if e.source_path!=f'presets/community/{e.id}/{e.version}':raise ValueError('预设投稿暂存路径不规范')
        return self


class RegistryReview(Contract):
    format: Literal['ember.registry-review/v1']='ember.registry-review/v1'
    kind: Literal['plugin','preset']
    id: ID
    version: VERSION
    decision: Literal['approve-catalog-entry','reject','needs-changes','archive','maintenance-needed','incompatible']
    reviewer: str=Field(min_length=1,max_length=80)
    reason: str=Field(min_length=1,max_length=2000)
    reviewed_at: str=Field(min_length=20,max_length=40)
    input_sha256: SHA256
    verification_sha256: SHA256 | None=None
    expected_index_sha256: SHA256 | None=None
    resulting_index_sha256: SHA256 | None=None
    scope: Literal['metadata-and-release-only']='metadata-and-release-only'
