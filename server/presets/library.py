"""Immutable, host-local data catalog. Packages are JSON blobs, never code installs."""
import json
from fastapi import HTTPException
from ..config import ROOT
from ..db import connection, now
from ..version import HOST_VERSION
from .codec import (load_folder, parse_envelope, canonical, PresetError,
                    MAX_CATALOG_BYTES, MAX_CATALOG_PACKAGES)


def put_package(con,package,source,user_id=None):
    identity=package.manifest['metadata']['id'];version=package.manifest['metadata']['version']
    prior=con.execute('SELECT package_hash FROM preset_packages WHERE preset_id=? AND version=?',(identity,version)).fetchone()
    if prior:
        if prior['package_hash']!=package.package_hash:
            raise HTTPException(409,'同一预设 ID / 版本已有不同内容；请提升作品版本，不覆盖旧房间来源')
        if user_id: con.execute('INSERT OR IGNORE INTO preset_access VALUES (?,?)',(package.package_hash,user_id))
        return False
    body=canonical(package.envelope()).decode('utf-8')
    row=con.execute('SELECT COUNT(*),COALESCE(SUM(length(CAST(bundle_json AS BLOB))),0) FROM preset_packages').fetchone()
    if row[0]>=MAX_CATALOG_PACKAGES or row[1]+len(body.encode())>MAX_CATALOG_BYTES:
        raise HTTPException(422,'本机预设库超过 128 个版本或 64 MiB，请先整理；不会删掉被房间引用的版本')
    con.execute('INSERT INTO preset_packages VALUES (?,?,?,?,?,?,?,?)',
                (package.package_hash,identity,version,body,source,user_id,now(),json.dumps(package.summary(),ensure_ascii=False)))
    if user_id: con.execute('INSERT OR IGNORE INTO preset_access VALUES (?,?)',(package.package_hash,user_id))
    return True


def seed_bundled(con):
    folder=ROOT/'presets'
    if not folder.exists(): return
    for path in sorted(folder.iterdir()):
        if path.is_dir() and not path.is_symlink() and (path/'preset.json').is_file():
            package=load_folder(path)
            put_package(con,package,'bundled')


def authorize_package(con,package_hash,user):
    row=con.execute("SELECT source FROM preset_packages WHERE package_hash=?",(package_hash,)).fetchone()
    if not row or (row['source']!='bundled' and not con.execute('SELECT 1 FROM preset_access WHERE package_hash=? AND user_id=?',(package_hash,user['id'])).fetchone()):
        raise HTTPException(404,'此预设精确版本不在你的本机作品库；散列不是读取权限')


def get_package(con,package_hash):
    row=con.execute('SELECT * FROM preset_packages WHERE package_hash=?',(package_hash,)).fetchone()
    if not row: raise HTTPException(404,'预设精确版本未在本机安装；请先预览并导入数据包')
    package=parse_envelope(json.loads(row['bundle_json']))
    if package.package_hash!=package_hash: raise HTTPException(409,'预设库存储内容校验失败；保留备份，不创建房间')
    return package


def compatibility(package,manager):
    manifest=package.manifest;blockers=[];warnings=[];resolved=[]
    current=tuple(map(int,HOST_VERSION.split('-')[0].split('.')))
    needed=tuple(map(int,manifest['minimum_host'].split('.')))
    if current<needed: blockers.append('作品需要宿主 '+manifest['minimum_host'])
    from ..rules import ENGINES
    engine=ENGINES.get(manifest['rule_system'])
    if not engine or engine.contract()['implementation_version']!=manifest['rule_version']:
        blockers.append('可执行规则版本不匹配；世界书文本不能替代规则适配器')
    for pin in manifest['plugins']:
        item=manager.items.get(pin['id']);reason=''
        if not item: reason='未安装'
        elif item['blocked']: reason='未获原部署者信任或模块不兼容'
        elif item['manifest']['version']!=pin['version'] or item['hash']!=pin['sha256']: reason='版本 / SHA256 不匹配'
        if reason:
            message=pin['id']+'：'+reason
            (blockers if pin['required'] else warnings).append(message)
        else: resolved.append(dict(pin))
    changed=True
    while changed:
        changed=False;ids={pin['id'] for pin in resolved}
        for pin in list(resolved):
            item=manager.items[pin['id']]
            missing=[dep for dep in item['manifest']['requires'] if dep not in ids or (pin['enabled'] and not next(other for other in resolved if other['id']==dep)['enabled'])]
            if missing:
                message=pin['id']+' 缺少已锁定且启用的依赖：'+','.join(missing)
                (blockers if pin['required'] else warnings).append(message)
                resolved.remove(pin);changed=True
    resources={};hosts=[]
    for pin in resolved:
        if not pin['enabled']: continue
        item=manager.items[pin['id']]
        if 'gm' in item['manifest']['hooks']: hosts.append(pin['id'])
        for resource in item['manifest']['provides']:
            if resource in resources: blockers.append('资源提供者冲突：'+resource)
            resources[resource]=pin['id']
    if len(hosts)>1: blockers.append('一次只能启用一个主持提供者')
    return {'can_create':not blockers,'blockers':list(dict.fromkeys(blockers)),
            'warnings':list(dict.fromkeys(warnings)),'plugins':resolved}


def catalog(manager,user):
    with connection() as con:
        rows=con.execute("SELECT p.* FROM preset_packages p WHERE p.source='bundled' OR EXISTS(SELECT 1 FROM preset_access a WHERE a.package_hash=p.package_hash AND a.user_id=?) ORDER BY p.preset_id,p.created_at DESC",(user['id'],)).fetchall()
        result=[]
        for row in rows:
            try:
                package=get_package(con,row['package_hash']);ready=compatibility(package,manager)
                result.append({**package.summary(),'source':row['source'],'compatibility':ready})
            except (PresetError,ValueError,HTTPException):
                result.append({'id':row['preset_id'],'version':row['version'],'package_hash':row['package_hash'],
                               'name':row['preset_id'],'source':row['source'],'data_only':True,
                               'compatibility':{'can_create':False,'blockers':['本机作品数据不完整；请保留备份排查'],'warnings':[]}})
        result.sort(key=lambda entry:(entry['id'],tuple(-int(part) for part in entry['version'].split('.'))))
        return result
