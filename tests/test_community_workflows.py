"""Preflight checks for reusable community workflows; these never invoke GitHub or publish.

The tests validate the workflow documents and syntax-check embedded Bash. They do not
claim that a third-party author has run the reusable workflows or published a release.
"""
import re
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
)


@pytest.mark.parametrize('relative', WORKFLOWS)
def test_community_workflow_yaml_permissions_and_pinned_actions(relative):
    path = ROOT / relative
    workflow = yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
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
    bash = shutil.which('bash')
    if not bash:
        pytest.skip('bash is unavailable; GitHub-hosted ubuntu-latest runs these workflows')
    path = ROOT / relative
    workflow = yaml.load(path.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    for job in workflow['jobs'].values():
        for step in job.get('steps', []):
            script = step.get('run')
            if not script:
                continue
            result = subprocess.run([bash, '-n'], input=script, text=True, capture_output=True)
            assert result.returncode == 0, f'{relative}: {step.get("name", "unnamed step")}\n{result.stderr}'


def test_creator_guide_reusable_workflow_examples_are_valid_yaml():
    text = (ROOT / 'docs/CREATOR_GUIDE.md').read_text(encoding='utf-8')
    examples = re.findall(r'```yaml\n(.*?)\n```', text, re.DOTALL)
    assert len(examples) == 2
    for example in examples:
        document = yaml.load(example, Loader=yaml.BaseLoader)
        assert document['jobs']
        assert document['permissions']['contents'] in ('read', 'write')
