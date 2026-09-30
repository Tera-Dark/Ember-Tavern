import React,{useEffect,useRef,useState} from 'react';
import {Puzzle,Map,Mic,FileText,Sparkles,Users,WandSparkles,ShieldCheck,Code2,RefreshCw,ChevronRight,Blocks,ExternalLink} from 'lucide-react';
import {api,getToken,requestKey} from './api.js';
const ICONS={map:Map,mic:Mic,file:FileText,spark:Sparkles,users:Users,wand:WandSparkles};
export function PluginIcon({name,...props}){const Icon=ICONS[name]||Puzzle;return <Icon {...props}/>;}
export function pluginGroups(room){
 const groups=new globalThis.Map();
 for(const p of room.plugins||[]){if(!p.enabled||!p.frontend||!p.ui?.group)continue;
  const id=p.ui.group;
  if(!groups.has(id))groups.set(id,{id,label:p.ui.label||p.name,icon:p.icon,plugins:[]});
  groups.get(id).plugins.push(p);
  if(p.ui.slot==='main'){groups.get(id).label=p.ui.label||p.name;groups.get(id).icon=p.icon;}
 }
 return [...groups.values()];
}
export function PluginCenter({room,onToggle,onRefresh,onGuide}){
 const active=(room.plugins||[]).filter(p=>p.enabled).length;
 useEffect(()=>{onRefresh();},[]);
 return <div className="page-scroll plugin-center"><div className="extension-intro"><div className="extension-symbol"><Blocks size={30} strokeWidth={1.4}/></div><div><span className="eyebrow">A SMALL HOST. AN OPEN WORLD.</span><h2>按需组装你的冒险桌。</h2><p>每个模块独立开关、独立状态。关掉地图或声音，故事照常进行。</p></div><span className="badge amber">SDK v1</span></div><div className="plugin-summary"><div><b>{room.plugins?.length||0}</b><span>已安装模块</span></div><div><b>{active}</b><span>本房已开启</span></div><div><ShieldCheck size={22}/><span>界面沙箱 · 后端显式信任</span></div><button onClick={onGuide}><Code2 size={16}/>开发插件<ChevronRight size={14}/></button></div><div className="section-title"><h2>模块清单</h2><button className="text-button" onClick={onRefresh}><RefreshCw size={13}/>刷新已安装清单</button></div><div className="plugins-grid">{(room.plugins||[]).map(p=><article className={'extension-card '+(p.enabled?'enabled':'')} key={p.id}><div className="extension-card-top"><span className="extension-card-icon"><PluginIcon name={p.icon} size={23} strokeWidth={1.5}/></span><span className="badge mini">{p.builtin?'随项目提供':'社区安装'} / {p.category||'扩展'}</span><button role="switch" aria-checked={p.enabled} aria-label={'开关 '+p.name} className={'plugin-switch '+(p.enabled?'on':'')} disabled={!room.is_owner||room.busy||!!p.blocked} onClick={()=>onToggle(p,!p.enabled)}><i/></button></div><h3>{p.name}<small>v{p.version}</small></h3><p>{p.description}</p><div className="extension-deps">{p.requires?.length?<><span>依赖</span>{p.requires.map(id=><code key={id}>{room.plugins.find(x=>x.id===id)?.name||id}</code>)}</>:<span>无强制依赖</span>}</div><footer><span className={'status-dot '+(!p.enabled?'muted-dot':'')}/>{p.blocked||p.fault||(p.enabled?'本房已启用':'关闭 · 数据保留')}<code>{p.id}</code></footer></article>)}</div><div className="extension-notice"><Puzzle size={20}/><div><h3>社区扩展有入口，不代表已凭空拥有一个社区。</h3><p>安装包放入插件目录即可发现；界面无需改宿主或重新打包。GitHub 仓库模板、发布清单、安装器和贡献规范已提供。未填写实际社区地址时，不展示虚假的在线市场。</p><button className="text-button" onClick={onGuide}>查看安装、开发与信任流程<ChevronRight size={13}/></button></div></div><p className="plugin-center-footnote">账号、权限、事件与回档属于最小内核，不可由插件拔掉或绕过。开关是房间配置，不随剧情回档；插件状态随快照恢复。</p></div>;
}

function palette(){const css=getComputedStyle(document.documentElement);return Object.fromEntries(['--bg','--surface','--surface-2','--border','--text','--muted','--faint','--gold','--green'].map(k=>[k,css.getPropertyValue(k).trim()]));}
function nonce(){return [...crypto.getRandomValues(new Uint8Array(16))].map(x=>x.toString(16).padStart(2,'0')).join('');}

function PluginFrame({plugin,room,user,apply,reload,notify,theme}){
 const iframe=useRef(null),roomRef=useRef(room),contextRef=useRef(null),ready=useRef(false),channel=useRef(nonce());
 const [failure,setFailure]=useState('');
 roomRef.current=room;
 const send=(kind,data,requestId,error)=>iframe.current?.contentWindow?.postMessage({ember:1,channel:channel.current,kind,data,requestId,error,...(kind==='reply'?{result:data}:{})},'*');
 async function updateContext(){
  try{const c=await api('/rooms/'+roomRef.current.id+'/extensions/'+plugin.id+'/context');c.theme=palette();c.voices=(window.speechSynthesis?.getVoices()||[]).map(v=>({name:v.name,lang:v.lang}));contextRef.current=c;setFailure('');if(ready.current)send('context',c);}catch(e){setFailure(e.message);}
 }
 useEffect(()=>{let disposed=false;
  const listener=async e=>{
   const m=e.data;
   if(disposed||e.source!==iframe.current?.contentWindow||m?.ember!==1||m.channel!==channel.current)return;
   const answer=(result,error)=>{if(!disposed)send('reply',result,m.requestId,error);};
   try{
    if(m.kind==='ready'){ready.current=true;await updateContext();return;}
    if(m.kind==='notify'){notify(String(m.message||'').slice(0,400),m.level==='error'?'error':'success');return;}
    const current=roomRef.current;
    if(!current.plugins.find(p=>p.id===plugin.id)?.enabled)throw new Error('模块已关闭');
    if(m.kind==='invoke'){
     const target=m.target||plugin.id,targetPlugin=current.plugins.find(p=>p.id===target);
     if(!targetPlugin?.enabled)throw new Error('目标模块未开启');
     if(target!==plugin.id&&!plugin.capabilities.includes('invoke:'+target+'.'+m.action)&&!Object.entries(contextRef.current?.resources||{}).some(([name,res])=>res?.owner===target&&plugin.capabilities.includes('invoke-resource:'+name+'.'+m.action)))throw new Error('插件未声明这项跨模块能力');
     const response=await api('/rooms/'+current.id+'/extensions/'+target+'/actions/'+encodeURIComponent(m.action),{method:'POST',body:{
      payload:m.payload||{},via:plugin.id,expected_plugin_revision:current.state._plugins?.[target]?.revision||0,expected_branch:current.branch,request_key:requestKey()}});
     apply(response.room);answer(response.output);await updateContext();return;
    }
    if(m.kind==='signal'){
     const target=m.target||plugin.id;
     if(target!==plugin.id&&!plugin.capabilities.includes('signal:'+target+'.'+m.name)&&!Object.entries(contextRef.current?.resources||{}).some(([name,res])=>res?.owner===target&&plugin.capabilities.includes('signal-resource:'+name+'.'+m.name)))throw new Error('插件未声明这个信号能力');
     window.dispatchEvent(new CustomEvent('ember-send-plugin-signal',{detail:{room_id:current.id,type:'plugin_signal',plugin_id:target,via:plugin.id,name:m.name,payload:m.payload||{},branch:current.branch}}));return;
    }
    if(m.kind==='speak'||m.kind==='stopSpeech'){
     if(!plugin.capabilities.includes('local:speech'))throw new Error('插件没有本地语音能力');
     if(!window.speechSynthesis)throw new Error('你的浏览器没有语音朗读支持');
     speechSynthesis.cancel();
     if(m.kind==='speak'){
      const text=String(m.text||'');if(!text.trim()||text.length>3000)throw new Error('朗读文本需1–3000字符');
      const voice=new SpeechSynthesisUtterance(text);voice.lang='zh-CN';voice.rate=Math.max(.5,Math.min(1.8,Number(m.options?.rate)||1));
      const chosen=speechSynthesis.getVoices().find(v=>v.name===m.options?.voice);if(chosen)voice.voice=chosen;
      voice.onerror=event=>notify('浏览器语音引擎无法朗读：'+event.error,'error');speechSynthesis.speak(voice);
     }
     answer({queued:true,source:'browser',saved:false});return;
    }
    if(['asset','downloadAsset','audio','downloadAudio'].includes(m.kind)){
     if(!plugin.capabilities.includes('asset:read')&&!plugin.capabilities.includes('asset:audio')||!String(m.assetId||'').match(/^[a-f0-9]{32}$/))throw new Error('非法音频请求');
     const response=await fetch('/api/rooms/'+current.id+'/assets/'+plugin.id+'/'+m.assetId,{headers:{Authorization:'Bearer '+getToken()}});
     if(!response.ok)throw new Error('音频不可用，可能已被回档、关闭或数据卷缺失');
     const blob=await response.blob();
     if(!plugin.capabilities.includes('asset:read')&&!blob.type.startsWith('audio/'))throw new Error('插件没有通用素材读取能力');
     if(m.kind==='downloadAudio'||m.kind==='downloadAsset'){
      const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='ember-asset-'+m.assetId.slice(0,8)+'.'+({'audio/mpeg':'mp3','audio/wav':'wav','image/png':'png','image/jpeg':'jpg','image/webp':'webp'}[blob.type]||'bin');a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);answer({downloaded:true});
     }else{
      const dataUri=await new Promise(resolve=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.readAsDataURL(blob);});answer({data_uri:dataUri});
     }
     return;
    }
    throw new Error('SDK 不支持此消息类型');
   }catch(error){answer(null,error.message);if(error.status===409)await reload().catch(()=>{});}
  };
  const signals=e=>{
   const m=e.detail;if(m.room_id!==roomRef.current.id||m.branch!==roomRef.current.branch)return;
   if(plugin.uses.some(name=>contextRef.current?.resources[name]?.owner===m.plugin_id))send('signal',m);
  };
  const voices=()=>updateContext();
  window.addEventListener('message',listener);window.addEventListener('ember-plugin-signal',signals);window.speechSynthesis?.addEventListener('voiceschanged',voices);
  return()=>{disposed=true;if(plugin.capabilities.includes('local:speech'))window.speechSynthesis?.cancel();window.removeEventListener('message',listener);window.removeEventListener('ember-plugin-signal',signals);window.speechSynthesis?.removeEventListener('voiceschanged',voices);};
 },[plugin.id]);
 useEffect(()=>{const timer=setTimeout(updateContext,40);return()=>clearTimeout(timer);},[room.revision,theme]);
 return <section className={'plugin-frame-wrap '+plugin.ui.slot}><div className="plugin-frame-label"><span><PluginIcon name={plugin.icon} size={12}/>{plugin.name}</span><small>隔离界面 · SDK v1</small></div>{failure&&<div className="plugin-frame-error">{failure} <button onClick={updateContext}>重试</button></div>}<iframe ref={iframe} title={'插件 · '+plugin.name} sandbox="allow-scripts" src={'/plugin-frame/'+plugin.id+'?bridge='+channel.current} style={{height:plugin.ui.height||500,display:failure?'none':'block'}}/></section>;
}
export function PluginWorkspace({group,room,...props}){
 const g=pluginGroups(room).find(x=>x.id===group);
 if(!g)return <div className="empty"><Puzzle size={32}/><h3>这组模块已关闭</h3><p>到模块中心开启后继续使用；已有数据不会因此被删除。</p></div>;
 return <div className="page-scroll extension-workspace"><div className="extension-workspace-note"><ShieldCheck size={14}/><span>每个面板独立沙箱运行，只能通过声明的 SDK 能力访问宿主。</span></div>{g.plugins.slice().sort((a,b)=>(a.ui.slot==='toolbar'?-1:1)-(b.ui.slot==='toolbar'?-1:1)).map(p=><PluginFrame key={p.id+':'+p.hash} plugin={p} room={room} {...props}/>)}</div>;
}
