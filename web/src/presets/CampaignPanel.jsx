import React from 'react';
import {BookOpen,Check,ArrowRight,KeyRound,ShieldCheck,Palette} from 'lucide-react';
import {Button} from '../components/ui';
import './presets.css';

export default function CampaignPanel({room,busy,onReveal,onAdvance,onTheme}){
  const campaign=room.state.campaign;if(!campaign)return null;
  const pending=!!room.state.pending_check||room.state.awaiting_gm;
  return <section className="campaign-panel">
    <div className="section-title"><h2><BookOpen size={20}/>剧本进度</h2><span className={'badge '+(campaign.completed?'green':'amber')}>{campaign.completed?'已收束':'进行中'}</span></div>
    <div className="campaign-heading"><b>{campaign.scene_title}</b><small>{campaign.preset.name} · v{campaign.preset.version}</small></div>
    <p className="campaign-objective">{campaign.objective}</p>
    <p className="campaign-policy">{campaign.profile.checks==='narrative'?'叙事模式 · 不自动提出检定':'轻规则 · 不确定行动由服务器检定'} · 线索与推进由房主确认，AI 不会自动判定结局。</p>
    <details className="campaign-brief"><summary>当前节点的开场与边界</summary><p>{campaign.brief}</p></details>
    <div className="revealed-clues"><h3>已揭示的线索</h3>{campaign.revealed_clues.length?campaign.revealed_clues.map(clue=><article key={clue.id}><Check size={15}/><div><b>{clue.title}</b><p>{clue.text}</p></div></article>):<p className="muted">还没有线索被房主正式揭示。叙事中的猜测不等于已确认事实。</p>}</div>
    {room.is_owner&&<details className="gm-workflow" open={!campaign.completed}><summary><ShieldCheck size={16}/>房主指引 · 不发给玩家</summary>
      <p className="gm-guidance">{campaign.gm_notes||'尊重角色选择，在获得证据后再确认剧情。'}</p>
      {pending&&<p className="preset-warning">有检定／主持待完成；先完成、取消或补述，再揭示和推进。</p>}
      {!!campaign.clues?.length&&<div className="gm-clues">{campaign.clues.map(clue=><article key={clue.id}><div><b>{clue.title}</b><p>{clue.text}</p>{clue.gm_notes&&<small>{clue.gm_notes}</small>}</div><Button className="outline compact" icon={KeyRound} disabled={busy||pending||clue.revealed} onClick={()=>onReveal(clue.id)}>{clue.revealed?'已揭示':'揭示 '+clue.title}</Button></article>)}</div>}
      <div className="campaign-transitions">{campaign.transitions?.map(edge=><article key={edge.id}><div><b>{edge.label}</b>{edge.gm_guidance&&<p>{edge.gm_guidance}</p>}{!edge.ready&&<small>{edge.requires_rule_status&&!edge.rule_status_ready?`仍需服务端规则状态：${edge.requires_rule_status}`:`仍需已揭示线索：${edge.requires_clues.join('、')}`}</small>}</div><Button className="primary compact" icon={ArrowRight} disabled={busy||pending||!edge.ready} onClick={()=>onAdvance(edge.id)}>推进：{edge.label}</Button></article>)}</div>
      {campaign.completed&&<p className="muted">结局不会自动重开。你可以回顾本场、继续自由叙事，或回档到一个有效节点。</p>}
    </details>}
    <div className="campaign-footer"><small>来源锁 {campaign.preset.package_hash.slice(0,16)}… · 库更新不会自动改变本场</small>{room.state.preset_theme&&onTheme&&<Button className="outline compact" icon={Palette} onClick={()=>onTheme(room.state.preset_theme)}>采用预设配色（仅个人界面）</Button>}</div>
    {room.is_owner&&campaign.lock&&<details className="campaign-lock"><summary>查看精确内容与模块锁</summary><code>{campaign.lock.package_hash}</code><ul>{campaign.lock.components.map(ref=><li key={ref.path}>{ref.kind} · {ref.id} @ {ref.version} <code>{ref.sha256.slice(0,16)}…</code></li>)}</ul><p>规则 {campaign.lock.rule.id} @ {campaign.lock.rule.version}</p><ul>{campaign.lock.plugins.map(pin=><li key={pin.id}>{pin.id} @ {pin.version} <code>{pin.sha256.slice(0,16)}…</code></li>)}</ul><p className="muted">这是开桌来源，不是禁止房主维护战役世界；房间编辑不会回写或升级原作品。</p></details>}
  </section>;
}
