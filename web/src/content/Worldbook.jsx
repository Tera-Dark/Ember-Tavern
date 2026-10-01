import React, {useState} from 'react';
import {BookOpen, Sparkles, Shield, CheckCircle2, Plus, Trash2, Check, LockKeyhole, Download, Upload, Eye, Power} from 'lucide-react';
import {Modal, Button, Empty} from '../components/ui.jsx';
import {requestKey} from '../api.js';

export function WorldPage({room, onImport, onExport}) {
  const world = room.state.world;
  return <div className="page-scroll">
    <div className="world-hero"><img src="/harbor.jpg" alt="世界书的雾港封面"/><div/><section><span className="eyebrow">WORLD DOSSIER / 当前时间线</span><h2>{world.title}</h2><span className="badge amber">{world.rule_system || 'ember-light/v1'}</span></section></div>
    {room.is_owner && <div className="content-action-bar"><Button className="outline compact" icon={Upload} onClick={onImport}>导入世界书</Button><Button className="ghost compact" icon={Download} onClick={onExport}>导出标准世界书</Button><small><LockKeyhole size={12}/>导出包含主持秘密，请审阅后分享</small></div>}
    <div className="world-premise"><span className="eyebrow">THE PREMISE</span><h3>故事的起点</h3><p>{world.premise}</p><div className="world-tone"><Sparkles size={15}/><span>叙事基调</span><b>{world.tone}</b></div></div>
    <div className="section-title"><h2>世界书条目<span>{world.lore.length}</span></h2><small>{room.is_owner ? '房主视图 · 秘密不会下发玩家端' : '公共设定 · 已按成员权限过滤'}</small></div>
    <div className="lore-grid">{world.lore.map((entry, index) => <article className={'lore-card ' + (entry.visibility === 'gm' ? 'private-entry ' : '') + (!entry.enabled ? 'disabled-entry' : '')} key={entry.id}>
      <div><BookOpen size={18}/><span className="mono">{String(index + 1).padStart(2, '0')}</span></div>
      <div className="lore-badges">{entry.kind === 'rule' && <span className="badge mini amber"><Shield size={10}/>桌面规则</span>}{entry.visibility === 'gm' && <span className="badge mini"><LockKeyhole size={10}/>仅主持</span>}{entry.activation === 'always' && <span className="badge mini">常驻</span>}{!entry.enabled && <span className="badge mini">已停用</span>}</div>
      <h3>{entry.title}</h3><p>{entry.content}</p><footer>{[...new Set([...(entry.keys || []), ...entry.tags.split(/\s+/).filter(Boolean)])].map(tag => <span key={tag}>{tag}</span>)}</footer>
    </article>)}</div>
    {!world.lore.length && <Empty icon={BookOpen} title="世界还有许多空白" description="房主可以添加地点、NPC、传闻、道具和桌面规则，供主持按需读取。"/>}
    <div className="rules-note"><Shield size={19}/><div><h3>服务端执行的规则</h3><p>{room.state.rules}</p><p className="creator-muted">世界书规则用于叙事约定，不能执行脚本、改写骰子或冒充完整 D&D / CoC 规则适配器。</p></div></div>
    {room.state.facts.length > 0 && <><div className="section-title"><h2>已经确认的事实<span>{room.state.facts.length}</span></h2></div><ul className="facts-list">{room.state.facts.map((fact, index) => <li key={index}><CheckCircle2 size={15}/>{fact}</li>)}</ul></>}
  </div>;
}

export function WorldModal({world, busy, isStale=false, onClose, onSave}) {
  const [fields, setFields] = useState(() => structuredClone(world));
  const edit = (key, value) => setFields(old => ({...old, [key]: value}));
  function editLore(index, key, value) {
    setFields(old => ({...old, lore: old.lore.map((entry, i) => i === index ? {...entry, [key]: value} : entry)}));
  }
  const add = () => edit('lore', [...fields.lore, {id: requestKey(), title: '', content: '', tags: '', keys: [], kind: 'lore', visibility: 'public', enabled: true, activation: 'keywords', priority: 0}]);
  return <Modal title="写下这个世界的边界" subtitle="公共条目供成员阅读；主持秘密仅房主与 AI 可读取。模型叙事仍需房主把关，不要写入凭据。" onClose={onClose} wide>
    <form className="form" onSubmit={e => {e.preventDefault(); onSave(fields);}}>
      {isStale&&<div className="info-box warning"><LockKeyhole size={16}/><p>房间在编辑期间已更新。为避免覆盖他人的修改，请复制未保存内容，关闭后重新编辑。</p></div>}
      <label>世界名称<input value={fields.title} onChange={e => edit('title', e.target.value)} required maxLength={80}/></label>
      <label>核心设定与开场前提<textarea value={fields.premise} onChange={e => edit('premise', e.target.value)} required rows={4} maxLength={4000}/></label>
      <label>叙事基调<input value={fields.tone} onChange={e => edit('tone', e.target.value)} maxLength={160}/></label>
      <div className="info-box small"><Shield size={16}/><p>可执行规则：{fields.rule_system || 'ember-light/v1'}。桌面规则优先进入有预算的上下文，但不替代服务器裁定。</p></div>
      <div className="section-title"><h3>世界书条目 <small>{fields.lore.length} / 160 · 总量 384 KiB</small></h3><Button type="button" className="outline compact" icon={Plus} disabled={fields.lore.length >= 160} onClick={add}>添加条目</Button></div>
      {fields.lore.map((entry, index) => <div className="lore-editor" key={entry.id}>
        <div><span className="mono">ENTRY {String(index + 1).padStart(2, '0')}</span><button className="icon-button" type="button" aria-label="移除此条目" onClick={() => edit('lore', fields.lore.filter((_, i) => i !== index))}><Trash2 size={15}/></button></div>
        <label>条目名称<input value={entry.title} required maxLength={80} onChange={e => editLore(index, 'title', e.target.value)}/></label>
        <div className="form-grid"><label><Shield size={12}/>条目类型<select value={entry.kind || 'lore'} onChange={e => editLore(index, 'kind', e.target.value)}><option value="lore">世界设定</option><option value="rule">桌面规则（优先常驻）</option></select></label><label><Eye size={12}/>可见范围<select value={entry.visibility || 'public'} onChange={e => editLore(index, 'visibility', e.target.value)}><option value="public">所有成员</option><option value="gm">仅主持（AI 可读）</option></select></label></div>
        <label>内容<textarea value={entry.content} required maxLength={3000} rows={3} onChange={e => editLore(index, 'content', e.target.value)}/></label>
        <label>触发关键词（用空格分隔）<input value={entry.tags} maxLength={120} onChange={e => editLore(index, 'tags', e.target.value)} placeholder="例如：灯塔 海港 守塔人"/></label>
        <EntryKeys keys={entry.keys||[]} onChange={keys=>editLore(index,'keys',keys)}/>
        <div className="form-grid three"><label>启用状态<select value={entry.enabled === false ? 'off' : 'on'} onChange={e => editLore(index, 'enabled', e.target.value === 'on')}><option value="on">启用</option><option value="off">停用（不进上下文）</option></select></label><label>激活方式<select value={entry.activation || 'keywords'} onChange={e => editLore(index, 'activation', e.target.value)}><option value="keywords">按关键词 / 相关度</option><option value="always">常驻（受预算约束）</option></select></label><label>优先级<input type="number" required min={-100} max={100} value={entry.priority || 0} onChange={e => editLore(index, 'priority', Number(e.target.value))}/></label></div>
      </div>)}
      <div className="form-footer"><Button className="ghost" type="button" onClick={onClose}>取消</Button><Button className="primary" icon={Check} disabled={busy||isStale}>保存世界书</Button></div>
    </form>
  </Modal>;
}

function EntryKeys({keys, onChange}) {
  const [text, setText] = useState(() => keys.join(', '));
  return <label>精确关键词 keys（逗号分隔，最多 24 项）<input value={text} maxLength={1464} onChange={event => {
    const value=event.target.value;
    setText(value);
    onChange(value.split(/[,，]/).map(key=>key.trim()).filter(Boolean));
  }} placeholder="例如：第十三盏灯, 守塔人"/></label>;
}
