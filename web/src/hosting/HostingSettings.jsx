import React from 'react';
import {Sparkles,BookOpen,Compass,ArrowRight,LockKeyhole,Pencil} from 'lucide-react';
import {Button} from '../components/ui';

export const MODE_LABELS={demo:'演示规则脚本',single:'真实单模型',live:'真实双模型'};
const models=[
  {key:'decision',icon:Compass,name:'结构化决策模型',tag:'NARRATIVE & DECISION',desc:'单模型入门只需此接口。叙事、事实和检定建议仍经过服务端校验。',protocol:'OpenAI 兼容 · chat/completions'},
  {key:'knowledge',icon:BookOpen,name:'世界知识顾问（高级可选）',tag:'SETTING & CONSISTENCY',desc:'只有显式选择双模型时才调用；不选择就不会产生知识顾问的请求费用。',protocol:'Gemini 原生 REST · generateContent'},
];
export default function HostingSettings({room,busy,onMode,onEnv,onNote,contextPreview}){
  const choices=[
    {id:'demo',title:'演示规则脚本',ready:room.models.demo_enabled,tag:'零模型调用',description:'无需密钥，可验证多人、骰子、记录和回档。使用固定分支与关键词规则，不具备通用 AI 叙事能力。'},
    {id:'single',title:'真实单模型主持',ready:room.models.single_ready,tag:'决策接口 · 可能收费',description:'只调用 OpenAI-compatible 决策模型。不需要 Gemini，不会偷偷调用知识顾问；已有世界书与检索证据仍进入上下文。'},
    {id:'live',title:'真实双模型主持',ready:room.models.live_ready,tag:'知识 + 决策 · 可能收费',description:'Gemini 知识顾问 → 决策模型 → 服务端校验。任一调用失败会明确报错，不会静默降级为演示脚本。'},
  ];
  return <div className="page-scroll">
    <div className="settings-intro"><Sparkles size={28}/><div><h2>先简单开桌，再按需增强。</h2><p>一个决策接口就能启用真实主持；世界知识顾问是高级选项。规则、骰子与权限始终由服务端掌握。</p></div></div>
    <div className="model-cards">{models.map(model=><article className="model-card" key={model.key}>
      <model.icon size={23}/><span className="eyebrow">{model.tag}</span><h3>{model.name}</h3><p>{model.desc}</p>
      <div><b>{room.models[model.key].provider}</b><code>{room.models[model.key].model}</code><small>{model.protocol}</small></div>
      <footer><span className={'status-dot '+(!room.models[model.key].configured?'muted-dot':'')}/>{room.models[model.key].configured?'服务端已配置（不代表联网或余额已验证）':'尚未配置 API'}<button onClick={onEnv}>配置说明<ArrowRight size={12}/></button></footer>
    </article>)}</div>
    <div className="settings-section"><div className="section-title"><h2>这张桌子的主持模式</h2><span className={'badge '+(room.ai_mode==='demo'?'amber':'green')}>{MODE_LABELS[room.ai_mode]||'未知模式'}</span></div>
      {choices.map(choice=><label key={choice.id} className={'mode-option '+(room.ai_mode===choice.id?'selected':'')+(!choice.ready?' disabled':'')}>
        <input type="radio" name="ai-mode" checked={room.ai_mode===choice.id} disabled={busy||!room.is_owner||!choice.ready} onChange={()=>onMode(choice.id)}/>
        <div><b>{choice.title}</b><p>{choice.description}</p></div><span className={'badge '+(choice.id==='demo'?'amber':'')}>{choice.ready?choice.tag:'需服务端配置'}</span>
      </label>)}
      <p className="settings-note"><LockKeyhole size={13}/>只有房主可切换。配置／切换本身不会测试模型或收费；发送行动、重试主持才会按所选模式请求服务。密钥不传给浏览器。</p>
    </div>
    {contextPreview}
    <div className="settings-section"><h3>人始终在桌边</h3><p>房主可以补述剧情、取消检定、维护角色和世界书，或回档。模型不能更改账号、角色操控权或历史分支；回档不撤销供应商计费。</p>{room.is_owner&&<Button className="outline" icon={Pencil} onClick={onNote}>写一段主持补述</Button>}</div>
  </div>;
}
