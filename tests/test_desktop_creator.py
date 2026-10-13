import json
from pathlib import Path
import pytest
from scripts.desktop_creator import operate, safe_error, project, DraftError


def make(tmp_path, kind='worldbook'):
    folder = tmp_path/'private-draft'
    result = operate({'operation':'create','directory':str(folder),'kind':kind,'identity':'qa-author-work','name':'Synthetic author draft'})
    return folder, result


def request(folder, revision, operation, **extra):
    return {'directory':str(folder),'revision':revision,'operation':operation,**extra}


def test_create_edit_validate_publication_and_immutable_package(tmp_path):
    folder, result = make(tmp_path)
    assert result['metadata']['authors'] == []
    assert result['metadata']['license'] == ''
    initial = (folder/'worldbook.json').read_bytes()
    publication = operate(request(folder,result['revision'],'publication'))
    assert publication['publication_ready'] is False
    assert publication['issues'] == ['authors_required','license_required']
    updated = operate(request(folder,result['revision'],'metadata',metadata={'version':'1.1.0','authors':['Synthetic QA'],'license':'MIT'}))
    assert (folder/'worldbook.json').read_bytes() != initial
    assert operate(request(folder,updated['revision'],'validate'))['valid']
    ready = operate(request(folder,updated['revision'],'publication'))
    assert ready['expected_tag'] == 'worldbook-qa-author-work-v1.1.0'
    output = tmp_path/'release.json'
    packaged = operate(request(folder,updated['revision'],'package',output=str(output)))
    assert len(packaged['archive_sha256']) == 64
    assert output.read_bytes() == (folder/'worldbook.json').read_bytes()
    original = output.read_bytes()
    with pytest.raises(DraftError,match='output_exists'):
        operate(request(folder,updated['revision'],'package',output=str(output)))
    assert output.read_bytes() == original


def test_external_edits_require_refresh_and_never_get_overwritten(tmp_path):
    folder, result = make(tmp_path)
    entry = folder/'worldbook.json'
    document = json.loads(entry.read_text(encoding='utf-8'))
    document['metadata']['name'] = 'Edited outside desktop'
    entry.write_text(json.dumps(document),encoding='utf-8')
    changed = entry.read_bytes()
    with pytest.raises(DraftError,match='source_changed'):
        operate(request(folder,result['revision'],'metadata',metadata={'name':'Stale UI'}))
    assert entry.read_bytes() == changed
    with pytest.raises(DraftError,match='output_exists'):
        operate(request(folder,project(folder)[0]['revision'],'package',output=str(folder/'inside.json')))


def test_preset_with_multiple_component_files_opens_and_explicitly_updates_only_draft_locks(tmp_path,monkeypatch):
    from scripts import creator
    monkeypatch.setattr(creator.settings,'data_dir',tmp_path/'isolated-data')
    folder, result = make(tmp_path,'preset')
    assert result['kind'] == 'preset'
    component = folder/'worldbook.json'
    # Locate the actual component rather than assuming the template layout.
    manifest = json.loads((folder/'preset.json').read_text(encoding='utf-8'))
    component = folder/manifest['worldbook']['path']
    raw = json.loads(component.read_text(encoding='utf-8'));raw['metadata']['name']='Edited component'
    component.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    refreshed = project(folder)[0]
    assert refreshed['kind'] == 'preset'
    locked = operate(request(folder,refreshed['revision'],'lock',refresh_plugins=False))
    assert locked['revision'] != result['revision']
    assert operate(request(folder,locked['revision'],'validate'))['valid']


def test_plugin_code_is_data_during_all_author_checks_and_packaging(tmp_path):
    folder, result = make(tmp_path,'plugin-backend')
    marker = tmp_path/'must-not-execute'
    (folder/'backend.py').write_text('from pathlib import Path\nPath('+repr(str(marker))+').write_text("executed")\nraise RuntimeError("must not import")\n',encoding='utf-8')
    refreshed = project(folder)[0]
    updated = operate(request(folder,refreshed['revision'],'metadata',metadata={'authors':['Synthetic QA'],'license':'MIT'}))
    assert operate(request(folder,updated['revision'],'validate'))['valid']
    assert operate(request(folder,updated['revision'],'publication'))['publication_ready']
    operate(request(folder,updated['revision'],'package',output=str(tmp_path/'plugin.zip')))
    assert not marker.exists()
    assert 'tags' not in json.loads((folder/'plugin.json').read_text(encoding='utf-8'))


def test_private_files_keys_and_exception_input_values_never_become_shareable_outputs(tmp_path):
    folder, result = make(tmp_path)
    secret = 'sk-'+'SyntheticCredentialOnly0123456789'
    (folder/'secret.private.json').write_text(json.dumps({'key':secret}),encoding='utf-8')
    with pytest.raises(DraftError,match='sensitive_file'):
        operate(request(folder,project(folder)[0]['revision'],'package',output=str(tmp_path/'release.json')))
    (folder/'secret.private.json').unlink()
    (folder/'notes.txt').write_text(secret,encoding='utf-8')
    with pytest.raises(DraftError,match='credential_detected'):
        operate(request(folder,project(folder)[0]['revision'],'publication'))
    try:
        operate(request(folder,project(folder)[0]['revision'],'metadata',metadata={'name':{'private':secret}}))
    except Exception as error:
        sanitized = safe_error(error)
        assert sanitized['code'] == 'contract_invalid'
        assert 'name' in sanitized['positions']
        assert secret not in json.dumps(sanitized)


def test_unknown_or_existing_destinations_and_symlinked_parents_are_not_modified(tmp_path):
    folder, result = make(tmp_path)
    before = (folder/'worldbook.json').read_bytes()
    with pytest.raises(DraftError,match='output_exists'):
        operate({'operation':'create','directory':str(folder),'kind':'worldbook','identity':'qa-new','name':'New'})
    assert (folder/'worldbook.json').read_bytes() == before
    with pytest.raises(DraftError,match='unsafe_path'):
        operate({'operation':'inspect','directory':'../outside'})
    link = tmp_path/'linked'
    try:
        link.symlink_to(folder,target_is_directory=True)
    except OSError:
        return
    with pytest.raises(DraftError,match='unsafe_path'):
        operate({'operation':'inspect','directory':str(link)})
