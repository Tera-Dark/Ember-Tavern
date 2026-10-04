import React, {useEffect,useMemo,useState} from 'react';
import {Activity,BookOpen,Check,Coins,LockKeyhole,Plus,RotateCcw,Shield,Trash2,Users} from 'lucide-react';
import {api,requestKey} from '../api.js';
import {Button,Empty} from '../components/ui.jsx';
import './workbench.css';

const VISIBILITY=[['public','公开'],['gm','仅主持']];
const QUEST_STATUS=[['proposed','待推进'],['active','进行中'],['paused','暂缓'],['completed','完成'],['failed','失败']];
const NPC_STATUS=[['unknown','未知'],['present','在场'],['missing','失踪'],['deceased','已故'],['ally','盟友'],['neutral','中立'],['hostile','敌对']];
const EMPTY={format:'ember.campaign-state/v1',quests:[],npcs:[],resources:[]};
const recordId=kind=>kind+'-'+(globalThis.crypto?.randomUUID?.().replaceAll('-','').slice(0,12)||Math.random().toString(36).slice(2,14));
const visibilityLabel=value=>value==='gm'?'仅主持':'公开';
const eventLabel=type=>({action:'行动',action_intent:'轮次行动',gm:'主持',gm_note:'房主补述',dice:'骰子',system:'系统',campaign_state:'状态',action_round:'轮次',world:'世界书',character:'角色',rewind:'回档',prologue:'开场',chat:'场外',error:'错误',extension:'模块'}[type]||type);

export default function CampaignWorkbench({room,busy,onLedgerSave,onModeChange,onSettleRound,onMemorySave,notify}){
  const ledger=room.state.campaign_state||EMPTY;
  const owner=room.is_owner;
  const mode=room.state.action_mode||'free';
  const round=room.state.action_round;
  const [memory,setMemory]=useState(null);
  const [summaryText,setSummaryText]=useState(room.state.memory_summary?.text||'');
  const [sourceIDs,setSourceIDs]=useState(room.state.memory_summary?.source_event_ids||[]);
  const [questDraft,setQuestDraft]=useState({title:'',summary:'',visibility:'public'});
  const [npcDraft,setNpcDraft]=useState({name:'',role:'',summary:'',visibility:'public'});
  const [resourceDraft,setResourceDraft]=useState({name:'',value:'0',unit:'',minimum:'0',maximum:'1000',visibility:'public'});
  const currentSources=useMemo(()=>memory?.sources||room.events.slice().reverse(),[memory,room.events]);

  useEffect(()=>{
    if(!owner){setMemory(null);return;}
    let alive=true;
    api('/rooms/'+room.id+'/memory').then(value=>{if(alive)setMemory(value);}).catch(error=>notify?.(error.message,'error'));
    return()=>{alive=false;};
  },[room.id,room.branch,room.revision,owner,notify]);
  useEffect(()=>{
    setSummaryText(room.state.memory_summary?.text||'');
    setSourceIDs(room.state.memory_summary?.source_event_ids||[]);
  },[room.id,room.branch,room.state.memory_summary?.updated_at]);

  async function saveLedger(next){return onLedgerSave(next);}
  async function patch(kind,id,changes){
    const next={...ledger,[kind]:ledger[kind].map(item=>item.id===id?{...item,...changes}:item)};
    await saveLedger(next);
  }
  async function remove(kind,id){
    if(!window.confirm('确认移除此条战役状态？该变更会进入事件记录，可通过回档恢复。'))return;
    await saveLedger({...ledger,[kind]:ledger[kind].filter(item=>item.id!==id)});
  }
  async function addQuest(e){
    e.preventDefault();const form=new FormData(e.currentTarget);
    const item={id:recordId('quest'),title:String(form.get('title')).trim(),summary:String(form.get('summary')).trim(),status:'proposed',visibility:String(form.get('visibility'))};
    if(await saveLedger({...ledger,quests:[...ledger.quests,item]}))setQuestDraft({title:'',summary:'',visibility:'public'});
  }
  async function addNpc(e){
    e.preventDefault();const form=new FormData(e.currentTarget);
    const item={id:recordId('npc'),name:String(form.get('name')).trim(),role:String(form.get('role')).trim(),summary:String(form.get('summary')).trim(),status:'unknown',relationship:0,visibility:String(form.get('visibility'))};
    if(await saveLedger({...ledger,npcs:[...ledger.npcs,item]}))setNpcDraft({name:'',role:'',summary:'',visibility:'public'});
  }
  async function addResource(e){
    e.preventDefault();const form=new FormData(e.currentTarget);
    const item={id:recordId('resource'),name:String(form.get('name')).trim(),value:Number(form.get('value')),unit:String(form.get('unit')).trim(),minimum:Number(form.get('minimum')),maximum:Number(form.get('maximum')),visibility:String(form.get('visibility'))};
    if(await saveLedger({...ledger,resources:[...ledger.resources,item]}))setResourceDraft({name:'',value:'0',unit:'',minimum:'0',maximum:'1000',visibility:'public'});
  }
  async function submitSummary(e){
    e.preventDefault();
    const result=await onMemorySave({text:summaryText,source_event_ids:sourceIDs});
    if(result){
      setMemory(old=>old?{...old,summary:result.state.memory_summary}:old);
      notify?.('主持记忆摘要已保存，并记录来源事件。');
    }
  }
  function toggleSource(id,checked){
    setSourceIDs(old=>checked?(old.includes(id)||old.length>=50?old:[...old,id]):old.filter(value=>value!==id));
  }
  async function settle(){
    const missing=round?.missing_character_ids?.length||0;
    if(missing&& !window.confirm('仍有 '+missing+' 个角色没有提交行动。确认以已提交的行动提前推进本轮？'))return;
    await onSettleRound();
  }

  return <div className="page-scroll campaign-workbench">
    <section className="m2-intro">
      <div className="m2-mark"><Activity size={22}/></div>
      <div><span className="eyebrow">M2 · CAMPAIGN STATE</span><h2>让战役状态可验证、可追溯</h2><p>任务、人物与资源由服务器保存快照；主持摘要保留来源；轮次行动由房主决定何时结算。</p></div>
      <span className="badge subdued">ember.campaign-state/v1</span>
    </section>

    <section className="round-card">
      <div className="m2-section-heading"><div><Users size={18}/><h3>多人行动协作</h3></div><span className={'badge '+(mode==='round'?'amber':'subdued')}>{mode==='round'?'小队轮次':'自由行动'}</span></div>
      <p className="m2-help">自由行动会立即交给主持；小队轮次允许分配角色各提交一次，再由房主手动结算。可提前结算缺席角色，不自动替玩家行动。</p>
      <div className="round-controls">
        <label>行动方式<select aria-label="行动方式" value={mode} disabled={!owner||busy} onChange={e=>onModeChange(e.target.value)}>
          <option value="free">自由行动 · 每次提交立即处理</option>
          <option value="round">小队轮次 · 收集后由房主结算</option>
        </select></label>
        {mode==='round'&&owner&&<Button className="primary compact" icon={Check} disabled={busy||!round?.submissions?.length||round?.status!=='collecting'} onClick={settle}>{round?.ready?'结算本轮':'提前结算已提交行动'}</Button>}
      </div>
      {mode==='round'?(round?<>
        <div className="round-progress"><b>第 {round.number} 轮</b><span>{round.submitted_count} / {round.required_count} 个已分配角色提交</span><i><em style={{width:(round.required_count?Math.min(100,round.submitted_count/round.required_count*100):0)+'%'}}/></i><small>{round.status==='collecting'?(round.ready?'所有参与者已提交，等待房主结算。':'行动仍在收集；房主可等待或提前结算。'):round.status==='waiting_check'?'主持已提出检定，完成检定后本轮结束。':round.status==='resolving'?'正在处理本轮行动…':'本轮已结算；下一位行动会开启新轮。'}</small></div>
        <div className="round-seats">{round.required.map(seat=><div key={seat.character_id} className={seat.submitted?'submitted':''}><span className="status-dot"/><b>{seat.character_name}</b><small>{seat.display_name}</small><span className="badge mini">{seat.submitted?'已提交':'等待行动'}</span></div>)}</div>
        {!!round.submissions?.length&&<div className="round-submissions">{round.submissions.map(item=><article key={item.character_id}><span>{item.character_name} · {item.actor_name}</span><p>{item.text}</p></article>)}</div>}
      </>:<div className="round-empty">尚未生成当前轮次。可在「冒险现场」选择角色并提交行动。</div>):<div className="round-empty">切换到小队轮次后，玩家行动会先收集，不会在每次提交后立即调用主持。</div>}
    </section>

    <div className="ledger-grid">
      <section className="ledger-card">
        <div className="m2-section-heading"><div><BookOpen size={18}/><h3>任务与目标 <small>{ledger.quests.length}</small></h3></div></div>
        <div className="ledger-list">{ledger.quests.length?ledger.quests.map(item=><article className="ledger-item" key={item.id}>
          <div className="ledger-item-main"><b>{item.title}</b><span className={'visibility '+(item.visibility==='gm'?'private':'')}><LockKeyhole size={11}/>{visibilityLabel(item.visibility)}</span></div>
          {item.summary&&<p>{item.summary}</p>}
          {owner&&<div className="ledger-item-controls"><select aria-label={'任务状态 '+item.title} value={item.status} disabled={busy} onChange={e=>patch('quests',item.id,{status:e.target.value})}>{QUEST_STATUS.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><select aria-label={'任务可见性 '+item.title} value={item.visibility} disabled={busy} onChange={e=>patch('quests',item.id,{visibility:e.target.value})}>{VISIBILITY.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><button className="m2-icon-button danger" aria-label={'删除任务 '+item.title} disabled={busy} onClick={()=>remove('quests',item.id)}><Trash2 size={14}/></button></div>}
        </article>):<Empty icon={BookOpen} title="尚无结构化任务" description="添加目标并记录当前进度；叙事文本不会自动结算任务。"/>}</div>
        {owner&&<form className="m2-add-form" onSubmit={addQuest}><label>任务名称<input aria-label="新任务名称" name="title" required maxLength={80} value={questDraft.title} onChange={e=>setQuestDraft({...questDraft,title:e.target.value})} placeholder="例如：找回失联的邮袋"/></label><label>摘要<input name="summary" maxLength={600} value={questDraft.summary} onChange={e=>setQuestDraft({...questDraft,summary:e.target.value})} placeholder="进展与完成条件"/></label><div><select aria-label="新任务可见性" name="visibility" value={questDraft.visibility} onChange={e=>setQuestDraft({...questDraft,visibility:e.target.value})}>{VISIBILITY.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><Button className="outline compact" icon={Plus} disabled={busy||!questDraft.title.trim()}>添加任务</Button></div></form>}
      </section>

      <section className="ledger-card">
        <div className="m2-section-heading"><div><Users size={18}/><h3>NPC 与关系 <small>{ledger.npcs.length}</small></h3></div></div>
        <div className="ledger-list">{ledger.npcs.length?ledger.npcs.map(item=><article className="ledger-item" key={item.id}>
          <div className="ledger-item-main"><b>{item.name}</b><span className="npc-role">{item.role||'身份未记录'}</span><span className={'visibility '+(item.visibility==='gm'?'private':'')}><LockKeyhole size={11}/>{visibilityLabel(item.visibility)}</span></div>
          {item.summary&&<p>{item.summary}</p>}
          <div className="npc-facts"><span>{item.status}</span><span>关系 {item.relationship>0?'+':''}{item.relationship} / 5</span></div>
          {owner&&<div className="ledger-item-controls"><select aria-label={'NPC状态 '+item.name} value={item.status} disabled={busy} onChange={e=>patch('npcs',item.id,{status:e.target.value})}>{NPC_STATUS.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><select aria-label={'NPC关系 '+item.name} value={item.relationship} disabled={busy} onChange={e=>patch('npcs',item.id,{relationship:Number(e.target.value)})}>{Array.from({length:11},(_,i)=>i-5).map(value=><option key={value} value={value}>{value>0?'+':''}{value}</option>)}</select><select aria-label={'NPC可见性 '+item.name} value={item.visibility} disabled={busy} onChange={e=>patch('npcs',item.id,{visibility:e.target.value})}>{VISIBILITY.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><button className="m2-icon-button danger" aria-label={'删除NPC '+item.name} disabled={busy} onClick={()=>remove('npcs',item.id)}><Trash2 size={14}/></button></div>}
        </article>):<Empty icon={Users} title="尚无结构化人物" description="NPC 关系只作为有界战役状态保存，不替代角色权限。"/>}</div>
        {owner&&<form className="m2-add-form" onSubmit={addNpc}><label>人物名称<input aria-label="新NPC名称" name="name" required maxLength={80} value={npcDraft.name} onChange={e=>setNpcDraft({...npcDraft,name:e.target.value})} placeholder="例如：渡船船长阿洛"/></label><label>身份<input name="role" maxLength={80} value={npcDraft.role} onChange={e=>setNpcDraft({...npcDraft,role:e.target.value})} placeholder="职业、所属阵营"/></label><label>公开描述／主持备注<input name="summary" maxLength={600} value={npcDraft.summary} onChange={e=>setNpcDraft({...npcDraft,summary:e.target.value})} placeholder="仅记录事实；主持秘密可设为仅主持"/></label><div><select aria-label="新NPC可见性" name="visibility" value={npcDraft.visibility} onChange={e=>setNpcDraft({...npcDraft,visibility:e.target.value})}>{VISIBILITY.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><Button className="outline compact" icon={Plus} disabled={busy||!npcDraft.name.trim()}>添加人物</Button></div></form>}
      </section>

      <section className="ledger-card">
        <div className="m2-section-heading"><div><Coins size={18}/><h3>资源计数 <small>{ledger.resources.length}</small></h3></div></div>
        <div className="ledger-list">{ledger.resources.length?ledger.resources.map(item=><ResourceItem key={item.id+':'+item.value} item={item} owner={owner} busy={busy} onSave={changes=>patch('resources',item.id,changes)} onRemove={()=>remove('resources',item.id)}/>):<Empty icon={Coins} title="尚无资源计数" description="资源更新只接受服务器约束范围内的整数；AI 叙事不会直接改数值。"/>}</div>
        {owner&&<form className="m2-add-form resource-add" onSubmit={addResource}><label>资源名称<input aria-label="新资源名称" name="name" required maxLength={80} value={resourceDraft.name} onChange={e=>setResourceDraft({...resourceDraft,name:e.target.value})} placeholder="例如：补给"/></label><div className="resource-range"><label>初始值<input name="value" type="number" required value={resourceDraft.value} onChange={e=>setResourceDraft({...resourceDraft,value:e.target.value})}/></label><label>下限<input name="minimum" type="number" required value={resourceDraft.minimum} onChange={e=>setResourceDraft({...resourceDraft,minimum:e.target.value})}/></label><label>上限<input name="maximum" type="number" required value={resourceDraft.maximum} onChange={e=>setResourceDraft({...resourceDraft,maximum:e.target.value})}/></label></div><div><input aria-label="资源单位" name="unit" maxLength={24} value={resourceDraft.unit} onChange={e=>setResourceDraft({...resourceDraft,unit:e.target.value})} placeholder="单位（可选）"/><select aria-label="新资源可见性" name="visibility" value={resourceDraft.visibility} onChange={e=>setResourceDraft({...resourceDraft,visibility:e.target.value})}>{VISIBILITY.map(([value,label])=><option key={value} value={value}>{label}</option>)}</select><Button className="outline compact" icon={Plus} disabled={busy||!resourceDraft.name.trim()}>添加资源</Button></div></form>}
      </section>
    </div>

    <section className="memory-card">
      <div className="m2-section-heading"><div><Shield size={18}/><h3>主持记忆摘要</h3></div><span className="badge subdued">带来源 · 按分支失效</span></div>
      <p className="m2-help">只保存房主审阅过的摘要；必须关联当前有效事件。封存未来不会进入上下文，回档会清除摘要。摘要是辅助记忆，不是正史或规则结算。</p>
      {owner?<form className="memory-form" onSubmit={submitSummary}>
        <label>摘要内容<textarea aria-label="主持记忆摘要" rows={5} maxLength={4000} value={summaryText} onChange={e=>setSummaryText(e.target.value)} placeholder="用简短文字记录已发生的要点、关系变化和仍待确认事项。避免把猜测写成事实。"/></label>
        <div className="memory-meta"><span>{summaryText.length} / 4000 字 · 模型上下文最多使用 {memory?.summary_context_budget_chars||3000} 字（还受总预算限制）</span><span>已选 {sourceIDs.length} 个来源</span></div>
        <div className="memory-sources"><b>选择来源事件（最多 50 条）</b>{currentSources.length?currentSources.slice(0,80).map(event=><label key={event.id} className="memory-source"><input type="checkbox" checked={sourceIDs.includes(event.id)} onChange={e=>toggleSource(event.id,e.target.checked)} disabled={busy||(!sourceIDs.includes(event.id)&&sourceIDs.length>=50)}/><span><small>#{event.seq} · {eventLabel(event.type)} · {event.actor_name}</small><span>{event.text}</span></span></label>):<small className="muted">尚无可绑定的当前时间线事件。</small>}</div>
        <div className="memory-actions"><Button className="outline compact" type="button" icon={RotateCcw} disabled={busy||(!summaryText&&!sourceIDs.length)} onClick={()=>{setSummaryText('');setSourceIDs([]);}}>清空草稿</Button><Button className="primary compact" icon={Check} disabled={busy||(!summaryText.trim()&&sourceIDs.length>0)||(summaryText.trim()&&!sourceIDs.length)}>保存摘要</Button></div>
        <small className="memory-notice">玩家和普通插件不会收到摘要正文或来源选择；真实模型调用仍可能把主持上下文发送给你配置的供应商。</small>
      </form>:<div className="memory-player-view">{room.state.memory_summary?.text?<><p>{room.state.memory_summary.text}</p><small>房主整理的辅助记忆 · 来源 {room.state.memory_summary.source_event_ids.length} 条</small></>:<p className="muted">房主尚未发布可见的记忆摘要。</p>}</div>}
    </section>
    <p className="m2-footnote">本面板实现固定的任务／NPC／资源契约，不执行表达式、不开放任意 JSON Patch。严格战斗或经济结算仍需独立规则适配器。</p>
  </div>;
}

function ResourceItem({item,owner,busy,onSave,onRemove}){
  const [value,setValue]=useState(String(item.value));
  useEffect(()=>setValue(String(item.value)),[item.value]);
  return <article className="ledger-item resource-item">
    <div className="ledger-item-main"><b>{item.name}</b><span className="resource-value">{item.value} {item.unit}</span><span className={'visibility '+(item.visibility==='gm'?'private':'')}><LockKeyhole size={11}/>{visibilityLabel(item.visibility)}</span></div>
    <small>有效范围 {item.minimum}–{item.maximum}{item.unit?' '+item.unit:''}</small>
    {owner&&<form onSubmit={e=>{e.preventDefault();onSave({value:Number(new FormData(e.currentTarget).get('value'))});}} className="ledger-item-controls"><input aria-label={'资源数值 '+item.name} type="number" name="value" min={item.minimum} max={item.maximum} value={value} disabled={busy} onChange={e=>setValue(e.target.value)}/><select aria-label={'资源可见性 '+item.name} value={item.visibility} disabled={busy} onChange={e=>onSave({visibility:e.target.value})}>{VISIBILITY.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select><Button className="outline compact" disabled={busy||Number(value)===item.value}>保存数值</Button><button type="button" className="m2-icon-button danger" aria-label={'删除资源 '+item.name} disabled={busy} onClick={onRemove}><Trash2 size={14}/></button></form>}
  </article>;
}
