"""Preflight checks for reusable community workflows; these never invoke GitHub or publish.

The tests validate the workflow documents and syntax-check embedded Bash. They do not
claim that a third-party author has run the reusable workflows or published a release.
"""
import re
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    '.github/workflows/community-validate.yml',
    '.github/workflows/community-preset-release.yml',
    '.github/workflows/community-plugin-release.yml',
    '.github/workflows/author-sdk-release.yml',
)


@pytest.mark.parametrize('relative', WORKFLOWS)
def test_community_workflow_yaml_permissions_and_pinned_actions(relative):
    path = ROOT / relative
    workflow = yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    if relative.endswith('author-sdk-release.yml'):
        assert workflow['on']['workflow_dispatch']['inputs']['publish']['default']=='false'
        assert workflow['permissions']['contents']=='read'
        assert workflow['jobs']['publish']['permissions']['contents']=='write'
    else:
        assert workflow['on']['workflow_call']['inputs']
        assert workflow['permissions']['contents'] == ('read' if relative.endswith('community-validate.yml') else 'write')
    assert workflow['jobs']
    for job in workflow['jobs'].values():
        for step in job.get('steps', []):
            reference = step.get('uses')
            if reference:
                assert '@' in reference, f'{relative}: action reference must be immutable: {reference}'
                owner, commit = reference.rsplit('@', 1)
                assert owner and re.fullmatch(r'[0-9a-f]{40}', commit), (
                    f'{relative}: action must use a full 40-character commit SHA: {reference}'
                )


@pytest.mark.parametrize('relative', WORKFLOWS)
def test_community_workflow_embedded_bash_syntax(relative):
    # Windows' bash.exe can be a WSL installation stub, not a usable shell.
    candidates=[shutil.which('bash')]
    if os.name=='nt':
        candidates.insert(0,str(Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Git/bin/bash.exe'))
    bash=None
    for candidate in candidates:
        if not candidate or not Path(candidate).is_file():continue
        try:
            probe=subprocess.run([candidate,'--version'],capture_output=True,timeout=10)
            if probe.returncode==0 and b'GNU bash' in probe.stdout:bash=candidate;break
        except (OSError,subprocess.TimeoutExpired):continue
    if not bash:
        pytest.skip('bash is unavailable; GitHub-hosted ubuntu-latest runs these workflows')
    path = ROOT / relative
    workflow = yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    for job in workflow['jobs'].values():
        for step in job.get('steps', []):
            script = step.get('run')
            if not script:
                continue
            result = subprocess.run([bash, '-n'], input=script, text=True, encoding='utf-8',errors='replace', capture_output=True)
            assert result.returncode == 0, f'{relative}: {step.get("name", "unnamed step")}\n{result.stderr}'


def test_creator_guide_reusable_workflow_examples_are_valid_yaml():
    text = (ROOT / 'docs/CREATOR_GUIDE.md').read_text(encoding='utf-8')
    examples = re.findall(r'```yaml\n(.*?)\n```', text, re.DOTALL)
    assert len(examples) == 2
    for example in examples:
        document = yaml.load(example, Loader=yaml.BaseLoader)
        assert document['jobs']
        assert document['permissions']['contents'] in ('read', 'write')


@pytest.mark.parametrize('relative',WORKFLOWS[1:3])
def test_release_workflows_share_local_publication_preflight(relative):
    workflow=yaml.load((ROOT/relative).read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
    scripts='\n'.join(step.get('run','') for job in workflow['jobs'].values() for step in job.get('steps',[]))
    assert 'scripts/creator.py release-check' in scripts and '--tag "$RELEASE_TAG"' in scripts
    assert 'tag must point to the source commit' in scripts
    assert 'gh release create' in scripts and '--verify-tag' in scripts
    assert 'scripts/community.py provenance' in scripts
    assert '--source-commit "$GITHUB_SHA"' in scripts and '--sdk-commit "$SDK_REF"' in scripts
    assert 'release/release-provenance.json --repo' in scripts


def test_author_sdk_release_checks_source_rights_and_refuses_asset_replacement():
    workflow=yaml.load((ROOT/WORKFLOWS[-1]).read_text(encoding='utf-8'),Loader=yaml.BaseLoader)
    scripts='\n'.join(step.get('run','') for step in workflow['jobs']['publish']['steps'])
    assert 'scripts/author_sdk.py build' in scripts and '--release' in scripts
    assert 'scripts/author_sdk.py verify' in scripts and '--sha256' in scripts
    assert 'SDK tag must point to the source commit' in scripts
    assert 'gh release view' in scripts and '--verify-tag' in scripts
    assert '--clobber' not in scripts
