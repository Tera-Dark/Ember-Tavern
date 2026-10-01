import React, {useEffect, useRef, useState} from 'react';
import {BookOpen, Users, Palette, Code2, Download, Upload, ShieldCheck, ArrowRight, Check, FileJson, LockKeyhole, AlertCircle, Loader2, Eye, RotateCcw, Copy, Sparkles, Search} from 'lucide-react';
import {api, downloadJSON, downloadFile, requestKey} from '../api.js';
import {Modal, Button} from '../components/ui.jsx';

const TYPES = {
  worldbook: {name: '世界书', icon: BookOpen, format: 'ember.worldbook/v1', description: '把地点、人物、桌面规则与主持秘密整理成可分享的世界。', note: '关键词 / 常驻 · 优先级 · 公共 / 主持可见', file: 'worldbook.json'},
  character: {name: '角色卡', icon: Users, format: 'ember.character/v1', description: '保存人物、属性与物品。导入的是一个角色，而不是一个账号。', note: '新建后再分配操控者 · 不导入权限', file: 'character.json'},
  theme: {name: '主题包', icon: Palette, format: 'ember.theme/v1', description: '让桌面有自己的气质。明暗配色也会传递到隔离插件界面。', note: '安全颜色令牌 · 本机偏好 · 无脚本或外网', file: 'theme.json'}
};
const REASONS = {rule: '规则优先', always: '常驻', keyword: '关键词', lexical: '相关度'};

export function CreatorWorkbench({room, appearance, onImport, notify}) {
  const [guide, setGuide] = useState(null);
  async function template(kind) {
    try {downloadJSON(await api('/creators/templates/' + kind), TYPES[kind].file); notify('模板已下载，修改后可在这里校验导入');}
    catch (error) {notify(error.message, 'error');}
  }
  async function openGuide() {
    try {setGuide((await api('/creators/guide')).text);}
    catch (error) {notify(error.message, 'error');}
  }
  return <div className="page-scroll creator-workbench">
    <section className="creator-intro"><div className="creator-emblem"><FileJson size={30} strokeWidth={1.3}/></div><div><span className="eyebrow">CREATE ONCE. BRING TO ANOTHER TABLE.</span><h2>把一个世界，交给下一张桌。</h2><p>创作不必从读源码开始。使用同一套模板、契约与校验器，先完成你的第一个作品。</p></div><span className="badge amber">创作契约 v1</span></section>
    <div className="creator-steps"><span><b>01</b>领取标准模板</span><ArrowRight size={14}/><span><b>02</b>填写、校验与预览</span><ArrowRight size={14}/><span><b>03</b>确认后应用</span><div><ShieldCheck size={15}/>预览不会写入剧情或调用 AI</div></div>
    <div className="creator-grid">{Object.entries(TYPES).map(([kind, type]) => <article className="creator-card" key={kind}>
      <div className="creator-card-heading"><span><type.icon size={23} strokeWidth={1.5}/></span><small>DATA CONTRACT / V1</small></div><h3>{type.name}</h3><code>{type.format}</code><p>{type.description}</p><div className="creator-card-note"><Check size={13}/>{type.note}</div>
      <div className="creator-card-actions"><Button className="outline compact" icon={Download} onClick={() => template(kind)}>下载模板</Button><Button className="primary compact" icon={Upload} disabled={kind !== 'theme' && !room.is_owner} onClick={() => onImport(kind)}>校验并{kind === 'theme' ? '应用' : '导入'}</Button></div>
      <button className="text-button creator-schema" onClick={() => downloadFile('/contracts/' + kind, kind + '.schema.json').catch(error => notify(error.message, 'error'))}>下载 JSON Schema<ArrowRight size={12}/></button>
    </article>)}</div>
    {!room.is_owner && <div className="creator-permission"><LockKeyhole size={15}/>世界书和角色由房主导入；你仍可下载模板创作，并应用个人主题。</div>}
    <div className="creator-lower"><section className="creator-plugin"><span className="eyebrow">FOR BUILDERS</span><h3><Code2 size={21}/>做一个模块，不必 fork 整间酒馆。</h3><p>纯 UI、Python 后端和骰盘桥接均有起步模板。地图、台本与 TTS 沿用版本化资源，关闭模块不会删除故事。</p><div className="creator-cli"><code>python scripts/creator.py init plugin-ui my-plugin --id my-plugin</code></div><div className="creator-plugin-footer"><span>静态校验 ≠ 安全审计 · Python 仍需显式信任</span><button className="text-button" onClick={openGuide}>创作与开发指南<ArrowRight size={13}/></button></div></section>
      <section className="creator-theme"><span className="eyebrow">YOUR PERSONAL TABLE</span><h3><Palette size={20}/>当前桌面</h3><b>{appearance.custom?.metadata.name || '余烬 · 默认主题'}</b><div className="theme-swatches">{['--bg', '--surface', '--gold', '--green', '--text'].map(token => <i key={token} style={{background: `var(${token})`}} title={token}/>)}</div><p>只保存在当前浏览器，不改变房间状态、规则或朋友的界面。主题缺少当前明暗配色时会使用默认配色。</p><Button className="outline compact" icon={RotateCcw} disabled={!appearance.custom} onClick={() => {appearance.reset(); notify('已恢复默认主题');}}>恢复默认主题</Button></section>
    </div>
    <div className="creator-footer"><ShieldCheck size={19}/><div><b>能分享素材，不意味着自动信任代码。</b><p>世界书、角色与主题都是数据；插件清单独立校验。凭据永不写入作品，公开分享前确认原作者授权与主持秘密。</p></div></div>
    {guide !== null && <Modal title="标准创作与开发指南" subtitle="数据格式、创作 CLI、插件模板与验收边界。" wide onClose={() => setGuide(null)}><pre className="plugin-guide-text">{guide}</pre></Modal>}
  </div>;
}

export function ImportModal({room, kind, appearance, apply, reload, notify, onClose, onImported}) {
  const type = TYPES[kind];
  const [document, setDocument] = useState(null), [file, setFile] = useState(null);
  const [mode, setMode] = useState('merge'), [preview, setPreview] = useState(null);
  const [checking, setChecking] = useState(false), [committing, setCommitting] = useState(false);
  const [error, setError] = useState(''), [acknowledged, setAcknowledged] = useState(false);
  const pendingKey = useRef(null);
  useEffect(() => {pendingKey.current = null;}, [document, mode]);
  useEffect(() => {
    if (!document) return;
    const controller = new AbortController();
    setChecking(true); setPreview(null); setError(''); setAcknowledged(false);
    const path = kind === 'theme' ? '/content/validate' : '/rooms/' + room.id + '/content/preview';
    const body = {kind, document, ...(kind === 'theme' ? {} : {mode})};
    api(path, {method: 'POST', body, signal: controller.signal}).then(setPreview).catch(err => {if (!controller.signal.aborted) setError(err.message);}).finally(() => {if (!controller.signal.aborted) setChecking(false);});
    return () => controller.abort();
  }, [document, mode, kind, room.id, room.revision]);
  async function choose(event) {
    const selected = event.target.files?.[0];
    if (!selected) return;
    setPreview(null); setError(''); setDocument(null); setFile(null);
    if (selected.size > 512 * 1024) {setError('文件不能超过 512 KiB，请拆分后导入。'); return;}
    try {
      const value = JSON.parse((await selected.text()).replace(/^\uFEFF/, ''));
      if (!value || Array.isArray(value) || typeof value !== 'object') throw new Error('文件顶层必须是 JSON 对象');
      setFile({name: selected.name, size: selected.size}); setDocument(value);
    } catch (err) {setError('无法读取 JSON：' + err.message);}
  }
  async function confirm() {
    if (!preview || committing || checking) return;
    setCommitting(true); setError('');
    try {
      if (kind === 'theme') {
        appearance.install(preview.document);
        notify('主题已应用到本机，插件界面也会收到配色');
      } else {
        pendingKey.current ||= requestKey();
        const result = await api('/rooms/' + room.id + '/content/import', {method: 'POST', body: {kind, document, mode, expected_revision: preview.revision, request_key: pendingKey.current}});
        apply(result); notify(type.name + '已导入，事件与回档快照已保存');
      }
      onImported(kind); onClose();
    } catch (err) {
      setError(err.message);
      if (err.status === 409) {notify('房间已更新，请检查新预览后重新确认。', 'error'); await reload().catch(() => {});}
    } finally {setCommitting(false);}
  }
  const requiresAcknowledgment = preview && (preview.warnings.length > 0 || (kind === 'worldbook' && mode === 'replace'));
  const entries = preview?.document.world?.lore || [];
  return <Modal title={'校验并' + (kind === 'theme' ? '应用主题包' : '导入' + type.name)} subtitle="只接受 JSON 数据。服务端重新校验；未知版本、脚本、权限字段和超限内容不会被执行。" onClose={onClose} wide>
    <div className="content-import">
      <label className="import-file"><Upload size={24}/><b>{file ? file.name : '选择创作文件'}</b><span>{file ? (file.size / 1024).toFixed(1) + ' KiB · 已读取，等待确认' : 'JSON · 最大 512 KiB · 不接受 PNG 角色卡或代码 ZIP'}</span><input aria-label="选择创作 JSON 文件" type="file" accept=".json,application/json" disabled={committing} onChange={choose}/></label>
      {kind === 'worldbook' && <div className="import-mode"><label>导入方式<select aria-label="导入方式" value={mode} onChange={e => setMode(e.target.value)} disabled={committing}><option value="merge">合并条目（同 ID 更新，保留世界前提）</option><option value="replace">替换世界书（覆盖设定及全部条目）</option></select></label><p>整本设定限 384 KiB。合并保留故事前提；替换只覆盖世界书，不清空角色或已发生剧情，可通过回档恢复。</p></div>}
      {checking && <div className="loading-inline"><Loader2 className="spin"/>正在使用服务端契约校验…</div>}
      {error && <div className="import-error" role="alert"><AlertCircle size={18}/><span>{error}</span></div>}
      {preview && <>
        <div className="import-summary"><div><span className="eyebrow">VALIDATED, NOT YET APPLIED</span><h3>{preview.summary.title || preview.summary.name}</h3><code>{preview.document.format} · v{preview.document.metadata.version}</code></div><ShieldCheck size={26}/></div>
        {kind === 'worldbook' && <><div className="import-metrics"><span><b>{preview.summary.entries}</b>条目</span><span><b>{preview.summary.rules}</b>桌面规则</span><span><b>{preview.summary.gm_only}</b>主持专属</span><span><b>{preview.summary.disabled}</b>停用</span></div><p className="creator-muted">本次新增 {preview.effects.added} / 更新 {preview.effects.updated} / 移除 {preview.effects.removed}；{mode === 'merge' ? '保留当前世界名称、前提和规则。' : '使用文件中的完整世界设定。'}</p><div className="import-entry-list">{entries.slice(0, 8).map(entry => <div key={entry.id}><span>{entry.visibility === 'gm' ? <LockKeyhole size={13}/> : <BookOpen size={13}/>}</span><b>{entry.title}</b><small>{entry.kind === 'rule' ? '规则' : '设定'} · {entry.visibility === 'gm' ? '仅主持' : '公共'} · {entry.enabled ? '启用' : '停用'}</small></div>)}{entries.length > 8 && <p className="creator-muted">还有 {entries.length - 8} 条；导入后可在世界书中编辑。</p>}</div></>}
        {kind === 'character' && <div className="import-character"><Users size={24}/><div><b>{preview.summary.archetype}</b><p>生命 {preview.summary.hp} / {preview.summary.max_hp} · {preview.summary.rule_system}</p><small>新增角色，不覆盖现有档案；房主需要另外分配操控者。</small></div></div>}
        {kind === 'theme' && <div className="import-theme">{Object.entries(preview.document.modes).filter(([, palette]) => palette).map(([name, palette]) => <div key={name}><b>{name === 'dark' ? '深色配色' : '浅色配色'}</b><div className="theme-swatches">{['--bg', '--surface', '--gold', '--green', '--text'].map(token => <i key={token} style={{background: palette[token]}}/>)}</div></div>)}</div>}
        {preview.warnings.length > 0 && <div className="import-warnings"><AlertCircle size={17}/><div><b>导入前请确认</b><ul>{preview.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></div></div>}
        {requiresAcknowledgment && <label className="import-ack"><input type="checkbox" checked={acknowledged} onChange={e => setAcknowledged(e.target.checked)}/>我已检查权限、规则与授权提示{mode === 'replace' && kind === 'worldbook' ? '，确认替换整个世界书' : ''}</label>}
      </>}
      <div className="form-footer"><Button className="ghost" onClick={onClose} disabled={committing}>取消</Button><Button className="primary" icon={committing ? Loader2 : Check} onClick={confirm} disabled={!preview || checking || committing || (requiresAcknowledgment && !acknowledged)}>{committing ? '正在应用…' : kind === 'theme' ? '应用个人主题' : '确认导入'}</Button></div>
    </div>
  </Modal>;
}

export function ContextPreview({room}) {
  const [query, setQuery] = useState(''), [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  async function inspect(event) {
    event.preventDefault(); setBusy(true); setError('');
    try {setPreview(await api('/rooms/' + room.id + '/gm/context-preview?q=' + encodeURIComponent(query)));}
    catch (err) {setError(err.message);}
    finally {setBusy(false);}
  }
  const selection = preview?.context._selection;
  return <section className="settings-section context-inspector"><div className="section-title"><h2><Eye size={18}/>主持上下文预览</h2><span className="badge">房主专属 · 无 API 费用</span></div><p>输入一次可能的行动，检查哪些设定会被选中。规则与常驻条目优先；停用条目与封存未来不会进入记忆。</p>
    <form className="context-search" onSubmit={inspect}><Search size={18}/><input aria-label="测试世界书激活" value={query} onChange={e => setQuery(e.target.value)} maxLength={2000} placeholder="例如：我向阿洛打听守塔人的去向"/><Button className="outline compact" icon={busy ? Loader2 : Eye} disabled={busy}>预览</Button></form>
    {error && <p className="danger-text" role="alert">{error}</p>}
    {selection && <div className="context-preview-result"><div><b>{selection.context_chars.toLocaleString()} / {selection.context_budget_chars.toLocaleString()}</b><span>序列化字符预算（不是 token 数）</span>{preview.revision !== room.revision && <strong>房间已更新，请重新预览</strong>}</div>{selection.entries.length ? <ul>{selection.entries.map(entry => <li key={entry.id}><span>{entry.visibility === 'gm' ? <LockKeyhole size={12}/> : <BookOpen size={12}/>}</span><b>{entry.title}</b><small>{REASONS[entry.reason]} · {entry.chars} 字符{entry.truncated ? ' · 已裁剪' : ''}</small></li>)}</ul> : <p className="creator-muted">没有激活的世界书条目，基础设定与有效事件仍会提供给主持。</p>}{selection.omitted_ids.length > 0 && <p className="creator-muted">{selection.omitted_ids.length} 条因预算或条数限制未加入；可提高优先级、缩短条目，或调整服务端预算。</p>}</div>}
  </section>;
}
