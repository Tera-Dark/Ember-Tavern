import React,{useEffect,useRef,useState} from 'react';
import {BookOpen,Upload,RefreshCw,ShieldCheck,Package,Check,AlertCircle} from 'lucide-react';
import {api,requestKey,downloadFile} from '../api';
import {Button} from '../components/ui';
import './presets.css';

const modes={investigation:'合作调查',adventure:'奇幻探索','slice-of-life':'日常与群像'};
export default function PresetLibrary({onCreated,notify,canImport=true,compact=false}){
  const [entries,setEntries]=useState([]),[selected,setSelected]=useState(''),[title,setTitle]=useState('我们的新冒险');
  const [hostPlays,setHostPlays]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [preview,setPreview]=useState(null),[confirmed,setConfirmed]=useState(false);
  const intent=useRef(null);
  const chosen=entries.find(item=>item.package_hash===selected);
  async function refresh(){const result=await api('/presets');setEntries(result.entries);}
  useEffect(()=>{let live=true;api('/presets').then(result=>{if(live)setEntries(result.entries);}).catch(value=>{if(live)setError(value.message);});return()=>{live=false;};},[]);
  async function work(fn){setBusy(true);setError('');try{await fn();}catch(value){setError(value.message);notify?.(value.message,'error');}finally{setBusy(false);}}
  async function create(){if(!chosen)return;await work(async()=>{
    const data={title:title.trim(),package_hash:chosen.package_hash,ai_mode:'demo',host_plays:hostPlays};
    const fingerprint=JSON.stringify(data);
    if(intent.current?.fingerprint!==fingerprint)intent.current={fingerprint,key:requestKey()};
    const room=await api('/rooms/from-preset',{method:'POST',body:{...data,request_key:intent.current.key}});
    intent.current=null;onCreated(room);
  });}
  async function inspect(file){if(!file)return;await work(async()=>{
    setPreview(null);setConfirmed(false);
    let payload;
    if(file.name.toLowerCase().endsWith('.zip')){
      if(file.size>1024*1024)throw new Error('预设 ZIP 最多 1 MiB；不会执行包内代码。');
      const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let index=0;index<bytes.length;index+=32768)binary+=String.fromCharCode(...bytes.subarray(index,index+32768));
      payload={archive_base64:btoa(binary)};
    }else if(file.name.toLowerCase().endsWith('.json')){
      if(file.size>2*1024*1024)throw new Error('规范 JSON 包最多 2 MiB');
      payload={document:JSON.parse(await file.text())};
    }else throw new Error('只支持数据预设 ZIP 或 ember.preset-bundle/v1 JSON');
    const result=await api('/presets/preview',{method:'POST',body:payload});setPreview({payload,result});
  });}
  async function install(){if(!preview||!confirmed)return;await work(async()=>{
    const result=await api('/presets/import',{method:'POST',body:{...preview.payload,expected_hash:preview.result.package_hash,confirm_data_only:true}});
    await refresh();setSelected(result.package_hash);setPreview(null);setConfirmed(false);notify?.('已导入数据包；没有安装或授权代码。');
  });}
  return <section className={'preset-library '+(compact?'compact':'')}>
    <div className="section-title"><div><span className="eyebrow">A COMPOSITION, NOT A PROMPT</span><h2><Package size={21}/>玩法预设库</h2></div><Button className="outline compact" icon={RefreshCw} disabled={busy} onClick={()=>work(refresh)}>刷新预设库</Button></div>
    <p className="preset-intro">选世界、剧本、角色和已审阅规则的一套组合。除通用轻规则外，M3 提供一条 SRD 5.2.1 有限战斗切片与一条原创合作 SLG-lite 经济实验；两者都不是完整 D&D 或完整 SLG。规则身份与版本固定在新房间，不自动覆盖旧冒险。</p>
    {error&&<div className="info-box warning" role="alert"><AlertCircle size={18}/><p>{error}</p></div>}
    <div className="gameplay-grid">{entries.map(entry=><button type="button" key={entry.package_hash} className={'gameplay-card '+(selected===entry.package_hash?'selected':'')} onClick={()=>{setSelected(entry.package_hash);setTitle(entry.name);}}>
      <span className="badge">{modes[entry.play_mode]||'待检查作品'}</span><h3>{entry.name}</h3><small>v{entry.version} · {entry.source==='bundled'?'内置原创样板':'本机作品'}</small><p>{entry.description||'作品说明待完善'}</p>
      <div className="gameplay-details"><span>{entry.min_players}–{entry.max_players} 位玩家</span><span>约 {entry.duration_minutes} 分钟</span><span>{entry.character_count} 张角色卡 · {entry.ending_count} 个结局</span></div>
      <span className={'gameplay-status '+(!entry.compatibility.can_create?'blocked':'')}>{entry.compatibility.can_create?'可按当前依赖开桌':'缺少匹配依赖／需修复'}</span>
      {selected===entry.package_hash&&<Check className="gameplay-check" size={18}/>}</button>)}</div>
    {!entries.length&&!error&&<p className="muted">本机还没有可用预设；旧入门世界仍可使用。升级宿主或导入经校验的数据包后刷新。</p>}
    {chosen&&<div className="chosen-preset"><div className="info-box small"><ShieldCheck size={18}/><p>固定版本 {chosen.version}，包散列 {chosen.package_hash.slice(0,16)}…；默认演示主持不调用外部模型。真实主持 / TTS 等显式生成可能收费。</p></div>
      <p>{chosen.content_warnings?.join('；')}</p>
      <p className="preset-warning">作品许可：{chosen.license||'未声明'}。分享前检查各组件授权；本机校验不等于再分发许可。</p>
      {!!chosen.warnings?.length&&<details><summary>作者／许可提醒（{chosen.warnings.length}）</summary>{chosen.warnings.map((warning,index)=><p className="preset-warning" key={index}>{warning}</p>)}</details>}
      {chosen.compatibility.blockers.map((item,index)=><p className="preset-warning" key={'block-'+index}>无法开桌：{item}</p>)}
      {chosen.compatibility.warnings.map((item,index)=><p className="muted" key={'optional-'+index}>可选模块：{item}，本场不会自动启用。</p>)}
      <form className="preset-create-form" onSubmit={event=>{event.preventDefault();create();}}><label>预设房间名称<input aria-label="预设房间名称" value={title} onChange={event=>setTitle(event.target.value)} maxLength={60} required/></label><label className="preset-checkbox"><input type="checkbox" checked={hostPlays} onChange={event=>setHostPlays(event.target.checked)}/>房主也操控第一位角色（不勾选则全部等待分配）</label><Button className="primary" icon={BookOpen} disabled={busy||!chosen.compatibility.can_create}>用此预设开新桌</Button></form>
      {canImport&&<button className="text-button" onClick={()=>downloadFile('/presets/'+chosen.package_hash+'/export',chosen.id+'-'+chosen.version+'.zip').catch(value=>setError(value.message))}>导出该精确数据版本（分享前检查许可）</button>}
    </div>}
    {canImport&&<div className="preset-import"><h3><Upload size={18}/>作者：导入数据预设</h3><p>ZIP 最多 1 MiB，仅接受清单声明的 JSON／说明文本。不执行 JS／Python／HTML，不携带 API Key，不自动下载安装依赖代码。</p><input aria-label="选择玩法预设包" type="file" accept=".zip,.json" disabled={busy} onChange={event=>{const file=event.target.files?.[0];event.target.value='';inspect(file);}}/>
      {preview&&<div className="preset-preview"><h4>导入预览 · {preview.result.summary.name}</h4><code>{preview.result.package_hash}</code><p>{preview.result.summary.scene_count} 个场景 · {preview.result.summary.ending_count} 个结局 · {preview.result.summary.character_count} 张角色卡</p>
        {[...preview.result.summary.warnings,...preview.result.compatibility.blockers,...preview.result.compatibility.warnings].map((item,index)=><p className="preset-warning" key={index}>{item}</p>)}
        <label className="preset-checkbox"><input aria-label="确认只导入数据并已检查许可" type="checkbox" checked={confirmed} onChange={event=>setConfirmed(event.target.checked)}/>我已检查来源、内容提醒与许可；只导入数据，不授予代码执行能力。</label><Button className="primary" icon={Check} disabled={busy||!confirmed} onClick={install}>确认导入预设数据</Button><Button className="ghost" disabled={busy} onClick={()=>{setPreview(null);setConfirmed(false);}}>取消预览</Button>
      </div>}
      <p className="muted">创作命令：init preset → lock-preset → validate → package-preset。完整教程见创作指南中的玩法预设手册。</p>
    </div>}
  </section>;
}
