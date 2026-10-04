"""M4 directory-contract regressions: metadata only, pinned artifacts, no installs."""
import copy
import json
from pathlib import Path
import shutil

import pytest

from server.config import ROOT
from scripts.registry import validate_registry


def _copy_registry_fixture(tmp_path, plugin_id='dice-tray', preset_id='echo-well-srd521'):
    data = json.loads((ROOT / 'registry/index.json').read_text(encoding='utf-8'))
    data['plugins'] = [copy.deepcopy(next(item for item in data['plugins'] if item['id'] == plugin_id))]
    data['preset_library'] = [copy.deepcopy(next(item for item in data['preset_library'] if item['id'] == preset_id))]
    root = tmp_path / 'repo'
    root.mkdir(parents=True)
    for relative in (data['plugins'][0]['template_path'], data['preset_library'][0]['source_path']):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
    for section in ('content_templates', 'gameplay_templates', 'core_schemas'):
        for item in data[section]:
            for field in ('template_path', 'schema_path'):
                relative = item.get(field)
                if not relative:
                    continue
                source = ROOT / relative
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    if data['plugins'][0]['package']:
        relative = data['plugins'][0]['package']
        target = root / 'plugin-packages' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'plugin-packages' / relative, target)
    (root / 'registry').mkdir(exist_ok=True)
    index = root / 'registry/index.json'
    index.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return root, index, data


def test_repository_catalog_is_valid_and_explicitly_offline():
    result = validate_registry()
    assert result['valid'] is True
    assert result['plugins_checked'] == 4
    assert result['presets_checked'] == 5
    assert result['code_executed'] is False
    assert result['network_access'] is False
    assert len(result['warnings']) == 2
    assert all('未联网验证' in warning for warning in result['warnings'])


def test_discovery_endpoint_exposes_local_metadata_without_installing_or_claiming_verification(client):
    response = client.get('/api/creators/registry')
    assert response.status_code == 200
    payload = response.json()
    assert payload['source'] == 'repository-local'
    assert payload['online_verified'] is False
    assert payload['auto_install'] is False
    assert len(payload['index']['plugins']) == 4
    assert len(payload['index']['preset_library']) == 5
    from server.version import HOST_VERSION
    assert payload['compatibility']['host_version'] == HOST_VERSION
    assert payload['compatibility']['host_version_policy'].startswith('numeric-base')
    assert all('requires' in item and 'provides' in item for item in payload['index']['plugins'])
    plugin_check = payload['compatibility']['plugins']['dice-tray@1.0.0']
    assert plugin_check['host_supported'] is True
    assert plugin_check['plugin_api_supported'] is True
    assert plugin_check['static_compatible'] is True
    assert plugin_check['local_installation_checked'] is False
    preset_check = payload['compatibility']['presets']['echo-well-srd521@1.0.0']
    assert preset_check['host_supported'] is True
    assert preset_check['plugin_api_supported'] is True
    assert preset_check['rule_implementation_supported'] is True
    assert preset_check['static_compatible'] is True
    assert preset_check['local_plugin_pins_checked'] is False
    assert '不会自动修改旧房间' in payload['notice']
    creator_index = client.get('/api/creators').json()
    assert creator_index['registry_url'] == '/api/creators/registry'
    assert creator_index['registry_schema_url'] == '/api/contracts/registry-index'
    assert client.get(creator_index['registry_schema_url']).status_code == 200


def test_registry_summary_tracks_plugin_requires_and_provides(tmp_path):
    root, index, data = _copy_registry_fixture(tmp_path, plugin_id='dice-tray')
    data['plugins'][0]['requires'] = ['missing-module']
    data['plugins'][0]['provides'] = ['sample.resource/v1']
    index.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='摘要与源码模板不符'):
        validate_registry(index, root=root)


def test_registry_plugin_declarations_are_unique_and_cannot_replace_core_resources():
    from server.contracts.registry import RegistryIndex

    data = json.loads((ROOT / 'registry/index.json').read_text(encoding='utf-8'))
    data['plugins'][0]['provides'] = ['core.events/v1']
    with pytest.raises(ValueError, match='core.*宿主资源'):
        RegistryIndex.model_validate(data)
    data['plugins'][0]['provides'] = []
    data['plugins'][0]['requires'] = [data['plugins'][0]['id'], data['plugins'][0]['id']]
    with pytest.raises(ValueError, match='不能重复'):
        RegistryIndex.model_validate(data)


def test_registry_host_compatibility_uses_numeric_base_not_beta_label():
    from server.content.routes import _registry_version_key

    assert _registry_version_key('2.4.0-beta.1') == _registry_version_key('2.4.0')
    assert _registry_version_key('2.5.0-beta.1') > _registry_version_key('2.4.0')


def test_registry_rejects_traversal_and_replay_hash_drift(tmp_path):
    root, index, data = _copy_registry_fixture(tmp_path)
    data['plugins'][0]['template_path'] = '../outside'
    index.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='registry 契约无效'):
        validate_registry(index, root=root)

    root, index, data = _copy_registry_fixture(tmp_path / 'second')
    data['preset_library'][0]['package_hash'] = '0' * 64
    index.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='package_hash 已漂移'):
        validate_registry(index, root=root)


def test_registry_checks_release_zip_digest_and_manifest(tmp_path):
    root, index, data = _copy_registry_fixture(tmp_path, plugin_id='session-insights')
    data['plugins'][0]['sha256'] = '0' * 64
    index.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='ZIP SHA256'):
        validate_registry(index, root=root)


def test_registry_reads_plugin_sources_as_data_without_executing_them(tmp_path):
    root, index, data = _copy_registry_fixture(tmp_path, plugin_id='scene-notes')
    plugin = data['plugins'][0]
    plugin.update(review_status='source-template-not-published', package=None, sha256=None,
                  download_url=None, download_note=None)
    marker = tmp_path / 'must-not-exist'
    backend = root / plugin['template_path'] / 'backend.py'
    backend.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n", encoding='utf-8')
    index.write_text(json.dumps(data), encoding='utf-8')
    result = validate_registry(index, root=root)
    assert result['valid'] is True
    assert result['code_executed'] is False
    assert not marker.exists()


def test_community_playtest_status_requires_clear_license_and_evidence():
    data = json.loads((ROOT / 'registry/index.json').read_text(encoding='utf-8'))
    data['preset_library'][0]['status'] = 'community-playtested'
    data['preset_library'][0]['evidence'] = []
    from server.contracts.registry import RegistryIndex
    with pytest.raises(ValueError, match='明确许可|证据链接'):
        RegistryIndex.model_validate(data)


def test_unlicensed_download_is_only_retained_as_a_legacy_reference():
    data = json.loads((ROOT / 'registry/index.json').read_text(encoding='utf-8'))
    data['plugins'][0]['review_status'] = 'archived'
    from server.contracts.registry import RegistryIndex
    with pytest.raises(ValueError, match='未获许可'):
        RegistryIndex.model_validate(data)
