import React,{useEffect,useMemo,useState} from 'react';
import {Activity,AlertCircle,ArrowRight,BedDouble,Check,CheckCircle2,Clock3,Coins,Dices,HeartPulse,Info,Mountain,Package,RefreshCw,Shield,Swords,TreePine,Users,Wheat,Wrench,XCircle} from 'lucide-react';
import {Button,Empty} from '../components/ui.jsx';
import './rules.css';

const ABILITIES=[
  ['strength','力量'],['dexterity','敏捷'],['constitution','体质'],
  ['intelligence','智力'],['wisdom','感知'],['charisma','魅力'],
];
const RESOURCES={food:'食物',timber:'木材',stone:'石料',coin:'银币'};
const RESOURCE_ICONS={food:Wheat,timber:TreePine,stone:Mountain,coin:Coins};
const BUILDINGS={farm:'农田',sawmill:'锯木场',quarry:'采石场',market:'集市'};
const BUILD_COST={farm:'3 木材 + 1 银币',sawmill:'4 木材 + 2 食物',quarry:'3 木材 + 2 食物',market:'2 木材 + 1 食物'};
const REPAIR_COST='4 木材 + 4 石料 + 2 食物';
const statusLabel={active:'进行中',completed:'目标完成',victory:'遭遇胜利',defeat:'遭遇失败',retreated:'已撤离',expired:'期限结束'};
const modifier=score=>Math.floor((Number(score)-10)/2);
const signed=value=>value>=0?'+'+value:String(value);

export default function RulesWorkbench({room,user,busy,onCommand}){
  const rules=room.state.game_rules;
  if(!rules)return <div className="page-scroll rules-workbench"><Empty icon={Dices} title="当前房间没有实验规则面板" description="规则工作台只会出现在锁定了受审阅规则适配器的 M3 预设中。"/></div>;
  const send=(endpoint,payload={},method='POST')=>onCommand(endpoint,{...payload,branch:room.branch},method);
  const common={room,user,rules,busy,send};
  const dnd=rules.adapter_id==='dnd5e-srd-5.2.1/v1';
  return <div className="page-scroll rules-workbench">
    <section className="m3-intro">
      <div className="m3-mark"><Activity size={22}/></div>
      <div className="m3-intro-copy"><span className="eyebrow">M3 · SERVER-AUTHORITATIVE RULES</span><h2>{dnd?'SRD 5.2.1 有限战斗切片':'灰烬边境合作经营'}</h2><p>{dnd?'角色数据、先攻、攻击和休息由服务器按一个有限 d20 子集结算；叙事文字不会代替命中或 HP 变化。':'共享资源、预留订单、生产和随机事件只在服务端回合结算后改变；叙事文字不会改写经济状态。'}</p></div>
      <div className="m3-version"><span className="badge amber">实验规则</span><code>{rules.adapter_id}</code><small>适配器版本 {rules.implementation_version||'未知'} · SHA256 {rules.implementation_sha256?.slice(0,12)||'未知'}…</small></div>
    </section>
    {dnd?<DndWorkbench {...common}/>:<CooperativeWorkbench {...common}/>} 
    <SupportBoundary dnd={dnd} rules={rules}/>
  </div>;
}

function DndWorkbench({room,user,rules,busy,send}){
  const encounter=rules.encounter;
  const active=encounter?.status==='active';
  const activeSeat=active&&encounter.current_index>=0?encounter.order[encounter.current_index]:null;
  const activeCharacter=activeSeat?.kind==='character'?room.state.characters.find(char=>char.id===activeSeat.character_id):null;
  const canControl=char=>room.is_owner||char?.assigned_to===user.id;
  const [foe,setFoe]=useState({name:'洞居兽（房主简化数据）',hit_points:12,armor_class:13,initiative_bonus:0,attack_bonus:3,damage_die:6,damage_bonus:1});
  const actorStatus=active?activeSeat?.kind==='foe'?'敌方行动':activeCharacter?`轮到 ${activeCharacter.name}`:'遭遇进行中':encounter?statusLabel[encounter.status]||encounter.status:'尚未开始';
  async function start(e){
    e.preventDefault();const f=new FormData(e.currentTarget);
    await send('/rules/dnd5e/encounters',{
      name:String(f.get('name')).trim(),hit_points:Number(f.get('hit_points')),
      armor_class:Number(f.get('armor_class')),initiative_bonus:Number(f.get('initiative_bonus')),
      attack_bonus:Number(f.get('attack_bonus')),damage_die:Number(f.get('damage_die')),
      damage_bonus:Number(f.get('damage_bonus')),
    });
  }
  return <>
    <section className="m3-panel dnd-turn-panel">
      <div className="m3-panel-heading"><div><Swords size={18}/><h3>遭遇与先攻</h3></div><span className={'badge '+(active?'amber':'subdued')}>{actorStatus}</span></div>
      <p className="m3-help">只录入本次实验遭遇所需的简化敌方数据；这不是怪物目录或官方怪物资料。服务器为所有角色和敌方掷先攻，并自动执行敌方单次攻击。</p>
      {encounter&&<div className="dnd-encounter-summary">
        <div className="encounter-topline"><div><span className="eyebrow">{active?'CURRENT ENCOUNTER':'LAST ENCOUNTER'}</span><h4>{encounter.foe.name}</h4></div><span className={'badge '+(encounter.status==='victory'?'green':encounter.status==='defeat'?'':'subdued')}>{statusLabel[encounter.status]||encounter.status}</span></div>
        <div className="foe-health"><span>敌方 HP</span><b>{encounter.foe.hit_points} / {encounter.foe.max_hit_points}</b><i><em style={{width:(encounter.foe.max_hit_points?100*encounter.foe.hit_points/encounter.foe.max_hit_points:0)+'%'}}/></i></div>
        {active&&<div className="dnd-round-strip"><span>第 {encounter.round} 轮</span><span>当前行动者：<b>{activeSeat?.name||'—'}</b></span><span>敌方 AC {encounter.foe.armor_class}</span></div>}
        <div className="initiative-order">{encounter.order.map((seat,index)=><div key={seat.character_id||'foe'} className={active&&index===encounter.current_index?'current':''}><span>{index+1}</span><b>{seat.name}</b><small>{seat.kind==='foe'?'敌方':'角色'} · 先攻 {seat.initiative}</small></div>)}</div>
        {active&&activeCharacter&&<div className="dnd-turn-actions"><div><b>现在由「{activeCharacter.name}」行动</b><small>{room.is_owner?'房主可代玩家操作；否则由角色操控者提交。':'只有该角色的操控者可以提交。'}</small></div><div><Button className="primary compact" icon={Swords} disabled={busy||!canControl(activeCharacter)} onClick={()=>send('/rules/dnd5e/actions',{character_id:activeCharacter.id,action:'attack'})}>单次武器攻击</Button><Button className="outline compact" icon={Shield} disabled={busy||!canControl(activeCharacter)} onClick={()=>send('/rules/dnd5e/actions',{character_id:activeCharacter.id,action:'dodge'})}>闪避</Button></div></div>}
        {active&&room.is_owner&&<Button className="ghost compact dnd-end-button" icon={XCircle} disabled={busy} onClick={()=>send('/rules/dnd5e/encounters/end',{})}>房主结束遭遇并撤离</Button>}
        {!!encounter.log?.length&&<details className="dnd-log"><summary>查看最近 {Math.min(encounter.log.length,40)} 条服务端结算记录</summary><div>{encounter.log.slice().reverse().map((item,index)=><p key={index}><small>第 {item.round} 轮</small>{item.text}</p>)}</div></details>}
      </div>}
      {!active&&room.is_owner&&<form className="m3-form dnd-foe-form" onSubmit={start}>
        <div className="m3-form-title"><b>{encounter?'开始下一次实验遭遇':'房主开启实验遭遇'}</b><span>所有数值由主持人明确输入</span></div>
        <label className="wide-field">遭遇名称<input name="name" value={foe.name} maxLength={80} required onChange={e=>setFoe({...foe,name:e.target.value})}/></label>
        <label>敌方 HP<input name="hit_points" type="number" min="1" max="300" value={foe.hit_points} onChange={e=>setFoe({...foe,hit_points:Number(e.target.value)})}/></label>
        <label>敌方 AC<input name="armor_class" type="number" min="5" max="30" value={foe.armor_class} onChange={e=>setFoe({...foe,armor_class:Number(e.target.value)})}/></label>
        <label>先攻修正<input name="initiative_bonus" type="number" min="-5" max="10" value={foe.initiative_bonus} onChange={e=>setFoe({...foe,initiative_bonus:Number(e.target.value)})}/></label>
        <label>攻击修正<input name="attack_bonus" type="number" min="-5" max="15" value={foe.attack_bonus} onChange={e=>setFoe({...foe,attack_bonus:Number(e.target.value)})}/></label>
        <label>伤害骰<select name="damage_die" value={foe.damage_die} onChange={e=>setFoe({...foe,damage_die:Number(e.target.value)})}>{[4,6,8,10,12].map(value=><option key={value} value={value}>d{value}</option>)}</select></label>
        <label>伤害修正<input name="damage_bonus" type="number" min="-5" max="15" value={foe.damage_bonus} onChange={e=>setFoe({...foe,damage_bonus:Number(e.target.value)})}/></label>
        <div className="m3-form-actions"><Button className="primary" icon={Dices} disabled={busy}>服务器掷先攻并开始</Button></div>
      </form>}
      {!room.is_owner&&!active&&<div className="m3-callout"><Info size={16}/><p>等待房主开启遭遇。遇敌不是强制路线；可以在剧本中交涉、绕行或撤退。</p></div>}
    </section>

    <section className="m3-panel">
      <div className="m3-panel-heading"><div><Users size={18}/><h3>实验角色卡</h3></div><span className="m3-count">{room.state.characters.length} 位角色</span></div>
      <p className="m3-help">可调字段显式标为手动值；本适配器不按职业／种族自动推导 AC 或 HP，也不含职业特性。能力值范围 3–20，等级仅 1–4。</p>
      <div className="dnd-sheet-grid">{room.state.characters.map(character=>{
        const sheet=rules.sheets[character.id];
        return <DndSheetCard key={character.id} character={character} sheet={sheet} owner={room.is_owner} busy={busy} canRest={canControl(character)&&!active} onSave={profile=>send(`/rules/dnd5e/sheets/${character.id}`,profile,'PUT')} onRest={kind=>send('/rules/dnd5e/rest',{character_id:character.id,kind})}/>;
      })}</div>
    </section>
    <div className="m3-note"><HeartPulse size={16}/><p>短休只消耗一枚生命骰并结算一次恢复；长休恢复满生命与部分生命骰。此实验版不追踪时长、食物、睡眠、中断或其他长休条件。</p></div>
  </>;
}

function DndSheetCard({character,sheet,owner,busy,canRest,onSave,onRest}){
  const defaults=useMemo(()=>({level:sheet?.level||1,ability_scores:{...(sheet?.ability_scores||Object.fromEntries(ABILITIES.map(([key])=>[key,10])))},armor_class:sheet?.armor_class||10,weapon_die:sheet?.weapon_die||6,weapon_ability:sheet?.weapon_ability||'strength',hit_die:sheet?.hit_die||8,max_hit_points:sheet?.max_hit_points||character.max_hp}),[sheet,character.max_hp]);
  const [draft,setDraft]=useState(defaults);
  const sheetKey=JSON.stringify(defaults);
  useEffect(()=>setDraft(defaults),[sheetKey]);
  const update=(key,value)=>setDraft(current=>({...current,[key]:value}));
  const updateAbility=(key,value)=>setDraft(current=>({...current,ability_scores:{...current.ability_scores,[key]:Number(value)}}));
  async function submit(e){e.preventDefault();await onSave({level:Number(draft.level),ability_scores:Object.fromEntries(ABILITIES.map(([key])=>[key,Number(draft.ability_scores[key])])),armor_class:Number(draft.armor_class),weapon_die:Number(draft.weapon_die),weapon_ability:draft.weapon_ability,hit_die:Number(draft.hit_die),max_hit_points:Number(draft.max_hit_points)});}
  return <article className="dnd-sheet-card">
    <header><div><h4>{character.name}</h4><span>{character.archetype} · {sheet?`等级 ${sheet.level}`:'等待初始化'}</span></div><span className="dnd-hp">HP <b>{sheet?.hit_points??character.hp}</b> / {sheet?.max_hit_points??character.max_hp}</span></header>
    <div className="dnd-sheet-combat-stats"><span><Shield size={14}/> AC <b>{sheet?.armor_class??'—'}</b></span><span><Dices size={14}/> 熟练 <b>+{sheet?.proficiency_bonus??'—'}</b></span><span><HeartPulse size={14}/> 生命骰 <b>{sheet?.hit_dice_remaining??'—'} / {sheet?.level??'—'}</b></span></div>
    <div className="dnd-ability-list">{ABILITIES.map(([key,label])=><div key={key}><span>{label}</span><b>{sheet?.ability_scores?.[key]??'—'}</b><small>{sheet? signed(modifier(sheet.ability_scores[key])):'—'}</small></div>)}</div>
    {owner&&<details className="dnd-sheet-edit"><summary>房主编辑实验角色卡</summary><form className="m3-form" onSubmit={submit}>
      <label>等级<select value={draft.level} onChange={e=>update('level',Number(e.target.value))}>{[1,2,3,4].map(value=><option key={value}>{value}</option>)}</select></label>
      <label>AC（手动值）<input type="number" min="5" max="30" value={draft.armor_class} onChange={e=>update('armor_class',Number(e.target.value))}/></label>
      <label>生命上限（手动值）<input type="number" min="1" max="100" value={draft.max_hit_points} onChange={e=>update('max_hit_points',Number(e.target.value))}/></label>
      <label>生命骰<select value={draft.hit_die} onChange={e=>update('hit_die',Number(e.target.value))}>{[6,8,10,12].map(value=><option key={value} value={value}>d{value}</option>)}</select></label>
      <label>武器伤害骰<select value={draft.weapon_die} onChange={e=>update('weapon_die',Number(e.target.value))}>{[4,6,8,10,12].map(value=><option key={value} value={value}>d{value}</option>)}</select></label>
      <label>武器主属性<select value={draft.weapon_ability} onChange={e=>update('weapon_ability',e.target.value)}><option value="strength">力量</option><option value="dexterity">敏捷</option></select></label>
      <div className="dnd-ability-editor">{ABILITIES.map(([key,label])=><label key={key}>{label}<input type="number" min="3" max="20" value={draft.ability_scores[key]} onChange={e=>updateAbility(key,e.target.value)}/></label>)}</div>
      <div className="m3-form-actions"><Button className="outline compact" icon={Check} disabled={busy}>保存规则角色卡</Button></div>
    </form></details>}
    {canRest&&<div className="dnd-rest-actions"><span>非遭遇期间可休息</span><div><Button className="outline compact" icon={BedDouble} disabled={busy||!sheet||sheet.hit_dice_remaining<=0||sheet.hit_points>=sheet.max_hit_points} onClick={()=>onRest('short')}>短休 · 消耗 1 骰</Button><Button className="ghost compact" icon={RefreshCw} disabled={busy||!sheet||(sheet.hit_points>=sheet.max_hit_points&&sheet.hit_dice_remaining===sheet.level)} onClick={()=>onRest('long')}>长休</Button></div></div>}
  </article>;
}

function CooperativeWorkbench({room,user,rules,busy,send}){
  const [action,setAction]=useState('repair');
  const [building,setBuilding]=useState('quarry');
  const [source,setSource]=useState('timber');
  const [destination,setDestination]=useState('stone');
  const [amount,setAmount]=useState(2);
  const orders=rules.orders||[];
  const planning=rules.status==='active'&&rules.phase==='planning';
  const canSubmit=planning&&!rules.my_order_submitted&&orders.length<room.members.length;
  const available=rules.available_resources||rules.resources;
  const last=rules.settlements?.slice(-3).reverse()||[];
  const production={farm:`${rules.buildings.farm*2} 食物`,sawmill:`${rules.buildings.sawmill*2} 木材`,quarry:`${rules.buildings.quarry*2} 石料`,market:`${rules.buildings.market} 银币`};
  async function submit(e){
    e.preventDefault();
    const order={action,amount:Number(amount)};
    if(action==='build')order.building=building;
    if(action==='trade'){order.source=source;order.destination=destination;}
    const result=await send('/rules/strategy/orders',order);
    if(result){setAction('repair');setAmount(2);}
  }
  return <>
    <section className={'m3-goal-card '+(rules.status==='completed'?'completed':rules.status==='expired'?'expired':'')}>
      <div className="m3-goal-symbol">{rules.status==='completed'?<CheckCircle2 size={24}/>:rules.status==='expired'?<XCircle size={24}/>:<Clock3 size={24}/>}</div>
      <div className="m3-goal-copy"><span className="eyebrow">TURN {rules.turn} / {rules.max_turns}</span><h3>{rules.goal}</h3><p>{rules.bridge_repairs} / {rules.goal_repairs} 段已修复 · {statusLabel[rules.status]||rules.status}</p></div>
      <div className="m3-goal-progress"><i><em style={{width:Math.min(100,100*rules.bridge_repairs/rules.goal_repairs)+'%'}}/></i><b>{Math.floor(100*rules.bridge_repairs/rules.goal_repairs)}%</b></div>
    </section>
    <div className="m3-economy-grid">
      <section className="m3-panel m3-resource-panel"><div className="m3-panel-heading"><div><Package size={18}/><h3>共享仓储</h3></div><span className="badge subdued">上限 1,000 / 种</span></div>
        <div className="m3-resource-grid">{Object.entries(RESOURCES).map(([key,label])=>{const Icon=RESOURCE_ICONS[key];return <article key={key}><span className="m3-resource-icon"><Icon size={17}/></span><span>{label}</span><b>{rules.resources[key]}</b><small>未被待结算订单预留：{available[key]}</small></article>;})}</div>
        <div className="m3-buildings"><b>建筑等级</b>{Object.entries(BUILDINGS).map(([key,label])=><span key={key}>{label}<b>{rules.buildings[key]} / 3</b></span>)}</div>
        <div className="m3-production"><b>下次结算基础产量</b>{Object.entries(production).map(([key,value])=><span key={key}>{BUILDINGS[key]}：{value}</span>)}</div>
      </section>
      <section className="m3-panel m3-order-panel"><div className="m3-panel-heading"><div><Wrench size={18}/><h3>提交合作订单</h3></div><span className="badge subdued">{orders.length} / {room.members.length} 已提交</span></div>
        <p className="m3-help">每位成员每回合一个订单。提交时会按当前库存预留资源；无效提议会被拒绝且不写入房间状态。</p>
        {!planning?<div className={'m3-terminal '+(rules.status==='completed'?'success':'')}><b>{statusLabel[rules.status]||rules.status}</b><span>{rules.status==='completed'?'三段水道已修复，玩法目标结束。':'期限已结束；当前局面保留在结算记录中。'}</span></div>:<>
          <form className="m3-order-form" onSubmit={submit}>
            <label>订单类型<select value={action} onChange={e=>setAction(e.target.value)}><option value="repair">修复一段水道 · {REPAIR_COST}</option><option value="build">建造建筑</option><option value="trade">交易资源</option></select></label>
            {action==='build'&&<><label>建筑<select value={building} onChange={e=>setBuilding(e.target.value)}>{Object.entries(BUILDINGS).map(([key,label])=><option key={key} value={key}>{label} · {BUILD_COST[key]}</option>)}</select></label></>}
            {action==='trade'&&<><div className="m3-trade-fields"><label>交出<select value={source} onChange={e=>setSource(e.target.value)}>{Object.entries(RESOURCES).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><label>换取<select value={destination} onChange={e=>setDestination(e.target.value)}>{Object.entries(RESOURCES).filter(([key])=>key!==source).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label></div><label>交易数量（偶数）<input type="number" min="2" max="10" step="2" value={amount} onChange={e=>setAmount(Number(e.target.value))}/></label><small className="m3-form-hint">{amount} 单位来源资源 → {amount/2} 单位目标资源</small></>}
            <Button className="primary" icon={ArrowRight} disabled={busy||!canSubmit||action==='trade'&&source===destination}>提交订单并预留资源</Button>
            {rules.my_order_submitted&&<small className="m3-submitted"><Check size={13}/>你本回合的订单已提交；请等待房主结算。</small>}
            {!rules.my_order_submitted&&orders.length>=room.members.length&&<small className="m3-form-hint">本回合成员订单已满，等待房主结算。</small>}
          </form>
        </>}
        {room.is_owner&&planning&&<Button className="outline m3-settle-button" icon={Check} disabled={busy||!orders.length} onClick={()=>send('/rules/strategy/settle',{})}>房主结算本回合</Button>}
      </section>
    </div>
    <section className="m3-panel m3-orders-current"><div className="m3-panel-heading"><div><Users size={18}/><h3>待处理订单</h3></div><span className="m3-count">按提交顺序执行</span></div>
      {orders.length?<div className="m3-order-list">{orders.map((order,index)=><article key={order.id}><span className="m3-order-number">{index+1}</span><div><b>{order.actor_name}</b><small>{orderLabel(order)}</small></div><span className="badge amber">待结算</span></article>)}</div>:<div className="m3-empty-orders">本回合还没有订单。请查看“未被预留”库存后选择建造、修复或交易。</div>}
    </section>
    <section className="m3-panel m3-settlements"><div className="m3-panel-heading"><div><Activity size={18}/><h3>服务端回合记录</h3></div><span className="m3-count">最近 {last.length} / {rules.settlements?.length||0} 回合</span></div>
      {last.length?<div className="m3-settlement-list">{last.map((item,index)=><article key={`${item.turn_resolved}-${index}`}><div className="m3-settlement-turn">第 {item.turn_resolved} 回合<span>{statusLabel[item.status]||item.status}</span></div><div className="m3-settlement-orders">{item.orders.map((order,i)=><p key={order.id||i}><b>{order.actor_name}</b>{order.detail}</p>)}</div><div className="m3-settlement-footer"><span>生产：{Object.entries(item.production).filter(([,value])=>value).map(([key,value])=>`${RESOURCES[key]} +${value}`).join('、')||'无'}</span><span>事件：{item.random_event?.name||'无'}</span></div><small>仓储变化：{Object.entries(item.resources_after).map(([key,value])=>`${RESOURCES[key]} ${item.resources_before[key]} → ${value}`).join(' · ')}</small></article>)}</div>:<Empty icon={Activity} title="尚无结算记录" description="首个订单结算后，服务器会保存资源、产量、随机事件和目标进度。"/>}
    </section>
    <div className="m3-callout"><AlertCircle size={17}/><p>事件骰由服务器秘密随机生成，并记录实际结果。相同初态、订单和随机序列会得到相同结算；玩家输入与 AI 叙事不提供随机数，也不能直接改库存。</p></div>
  </>;
}

function orderLabel(order){
  if(order.action==='repair')return '修复一段水道 · '+REPAIR_COST;
  if(order.action==='build')return '建造 '+(BUILDINGS[order.building]||order.building)+' · '+BUILD_COST[order.building];
  return `交易 ${order.amount} ${RESOURCES[order.source]} → ${order.amount/2} ${RESOURCES[order.destination]}`;
}

function SupportBoundary({dnd,rules}){
  const unsupported=rules.not_supported||[];
  return <section className="m3-boundary"><div className="m3-panel-heading"><div><Info size={18}/><h3>规则边界与版本声明</h3></div><span className="badge subdued">{dnd?'SRD 5.2.1 / 5.5e 核心机制':'原创 SLG-lite 实验'}</span></div>
    {dnd&&<p>规则身份 `dnd5e-srd-5.2.1/v1` 明确指向 SRD 5.2.1。官方说明 SRD 5.2 系列采用 5.5e 核心规则用语与机制；它不是 2014 规则。本面板不会把未实现的类别冒充成可执行规则。</p>}
    <b>当前未支持</b><div className="m3-boundary-tags">{unsupported.map(item=><span key={item}>{item}</span>)}</div>
    {!dnd&&<p>不是完整 SLG：没有玩家对抗、私人视野、外交战斗、多城管理、队列、动态市场、科技树或用户脚本。目标状态与叙事场景分开，房主需手动推进结局。</p>}
    {dnd&&<p>短休／长休由适配器有限结算，但没有追踪休息时长与中断条件；生命上限、AC、武器骰和能力值是房主明确填写的通用实验角色卡字段，不会由缺失的职业／装备规则推导。</p>}
  </section>;
}
