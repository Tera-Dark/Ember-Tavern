import React,{useCallback,useEffect,useMemo,useState} from 'react';
import {AlertCircle,ExternalLink,Package,Puzzle,RefreshCw,Search,ShieldCheck} from 'lucide-react';
import {api} from '../api.js';
import {Button} from '../components/ui.jsx';

const STATUS={
  'example':{label:'示例',tone:'neutral'},
  'source-template-not-published':{label:'源码模板 · 未发行',tone:'neutral'},
  'legacy-reference-only':{label:'历史引用 · 未复核',tone:'warning'},
  'community-submitted':{label:'社区投稿 · 未代表试玩',tone:'community'},
  'community-playtested':{label:'社区试玩',tone:'community'},
  'official-recommended':{label:'官方推荐',tone:'recommended'},
  'incompatible':{label:'不兼容',tone:'warning'},
  'archived':{label:'已归档',tone:'neutral'},
  'original-playtest-example':{label:'原创示例 · 非社区试玩',tone:'neutral'},
  'experimental-playable-vertical-sample':{label:'实验样板 · 非完整规则',tone:'warning'}
};
const MAINTENANCE={active:'维护中','maintenance-needed':'需要维护',unmaintained:'无人维护',unknown:'维护状态未知',archived:'已归档'};
const KIND={preset:'玩法预设',plugin:'代码模块'};
const isUnlicensed=value=>!value||['UNLICENSED','UNDECLARED'].includes(value.trim().toUpperCase());
const safeExternal=value=>typeof value==='string'&&value.startsWith('https://');

function CompatibilitySummary({kind,result,currentHost}){
  if(!result)return <div className="registry-compatibility pending">兼容性尚未计算。</div>;
  const requirements=kind==='preset'?result.rule_implementation_supported:result.plugin_api_supported;
  const host=result.host_supported;
  const staticOk=result.static_compatible;
  const unlisted=kind==='plugin'?result.required_modules_not_in_directory||[]:[];
  return <div className={'registry-compatibility '+(staticOk?'static-ok':'static-warning')}>
    <b>{kind==='preset'?'宿主 / API / 规则':'宿主 / API'} 静态{staticOk?'匹配':'不匹配'}</b>
    <span>宿主 {currentHost||'版本未知'} · {host?'满足最低版本':'低于最低版本'} · Plugin API {result.plugin_api_supported?'匹配':'不匹配'}{kind==='preset'&&` · 规则实现 ${requirements?'匹配':'不匹配'}`}</span>
    {unlisted.length>0&&<span>目录未收录的 requires：{unlisted.join('、')}</span>}
    {kind==='preset'&&result.required_plugin_pins>0&&<span>{result.required_plugin_pins} 个模块锁尚未对本机安装状态核验。</span>}
    <small>最低宿主按数字基版比较（不区分 beta）。不代表安全审计、模块已安装或作品可运行；本机安装状态未检查。</small>
  </div>;
}

function CatalogCard({kind,item,compatibility,currentHost}){
  const status=STATUS[item.status||item.review_status]||{label:item.status||item.review_status||'未分级',tone:'neutral'};
  const published=Boolean(item.download_url)&&!isUnlicensed(item.license)&&item.status!=='legacy-reference-only'&&item.review_status!=='legacy-reference-only';
  const warnings=kind==='preset'?item.content_warnings||[]:[];
  const plugins=kind==='preset'?item.plugins||[]:[];
  return <article className="registry-card">
    <div className="registry-card-top"><span className="registry-kind">{kind==='preset'?<Package size={15}/>:<Puzzle size={15}/>} {KIND[kind]}</span><span className={'registry-status '+status.tone}>{status.label}</span></div>
    <h3>{item.name||item.id}</h3>
    <div className="registry-identity"><code>{item.id}</code><span>v{item.version}</span></div>
    <p className="registry-description">{item.description||'作者尚未填写作品说明。'}</p>
    <dl className="registry-facts">
      {kind==='preset'?<>
        <div><dt>规则</dt><dd><code>{item.rule_system}</code> · {item.rule_version}</dd></div>
        <div><dt>最低宿主 / API</dt><dd>{item.minimum_host} / Plugin API {item.plugin_api}</dd></div>
        <div><dt>桌型</dt><dd>{item.play_mode} · {item.min_players}–{item.max_players} 人 · 约 {item.duration_minutes} 分钟</dd></div>
        {!!plugins.length&&<div><dt>精确模块锁</dt><dd>{plugins.map(pin=><span className="registry-pin" key={pin.id}>{pin.id}@{pin.version} · {pin.sha256.slice(0,12)}…{pin.required?'（必需）':'（可选）'}</span>)}</dd></div>}
      </>:<>
        <div><dt>分类</dt><dd>{item.category||'扩展'}</dd></div>
        <div><dt>最低宿主 / API</dt><dd>{item.minimum_host} / Plugin API {item.api_version}</dd></div>
        <div><dt>能力</dt><dd>{item.capabilities?.length?item.capabilities.map(value=><span className="registry-chip" key={value}>{value}</span>):'未声明'}</dd></div>
        {!!item.requires?.length&&<div><dt>依赖模块</dt><dd>{item.requires.map(value=><span className="registry-chip" key={value}>{value}</span>)}</dd></div>}
        {!!item.uses?.length&&<div><dt>读取资源</dt><dd>{item.uses.map(value=><span className="registry-chip" key={value}>{value}</span>)}</dd></div>}
        {!!item.provides?.length&&<div><dt>提供资源</dt><dd>{item.provides.map(value=><span className="registry-chip" key={value}>{value}</span>)}</dd></div>}
      </>}
      <div><dt>作者 / 许可</dt><dd>{item.authors?.length?item.authors.join('、'):'未填写'} / {item.license||'未声明'}</dd></div>
      <div><dt>维护状态</dt><dd>{MAINTENANCE[item.maintenance_status]||'未知'}</dd></div>
    </dl>
    <CompatibilitySummary kind={kind} result={compatibility} currentHost={currentHost}/>
    {warnings.length>0&&<div className="registry-warnings"><b>内容提醒</b><ul>{warnings.map((warning,index)=><li key={index}>{warning}</li>)}</ul></div>}
    <div className="registry-card-footer">
      <span className="registry-hash">{kind==='preset'?'内容锁':'包 SHA'} · {(kind==='preset'?item.package_hash:item.sha256||'未发行').slice(0,16)}{(kind==='preset'?item.package_hash:item.sha256)?'…':''}</span>
      {kind==='preset'&&item.archive_sha256&&<span className="registry-hash">发布方归档 SHA · {item.archive_sha256.slice(0,16)}…（未联网复核）</span>}
      <div className="registry-links">
        {published?<a href={item.download_url} target="_blank" rel="noreferrer">下载页面 <ExternalLink size={12}/></a>:<span className="registry-no-download">{item.review_status==='legacy-reference-only'?'旧链接未核验；不提供下载入口':item.download_url&&isUnlicensed(item.license)?'许可未明确；不提供下载入口':'暂无公开下载'}</span>}
        {safeExternal(item.source_url)&&<a href={item.source_url} target="_blank" rel="noreferrer">源码 <ExternalLink size={12}/></a>}
        {safeExternal(item.issue_url)&&<a href={item.issue_url} target="_blank" rel="noreferrer">维护渠道 <ExternalLink size={12}/></a>}
        {!!item.evidence?.length&&<details><summary>证据（{item.evidence.length}）</summary>{item.evidence.map((url,index)=><a key={url} href={url} target="_blank" rel="noreferrer">证据 {index+1} <ExternalLink size={12}/></a>)}</details>}
      </div>
    </div>
  </article>;
}

export default function RegistryExplorer(){
  const [payload,setPayload]=useState(null),[query,setQuery]=useState(''),[kind,setKind]=useState('all'),[status,setStatus]=useState('all');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const load=useCallback(async()=>{setBusy(true);setError('');try{setPayload(await api('/creators/registry'));}catch(value){setError(value.message);}finally{setBusy(false);}},[]);
  useEffect(()=>{load();},[load]);
  const index=payload?.index;
  const entries=useMemo(()=>{
    const all=[...(index?.preset_library||[]).map(item=>({kind:'preset',item})),...(index?.plugins||[]).map(item=>({kind:'plugin',item}))];
    const needle=query.trim().toLocaleLowerCase();
    return all.filter(({kind:entryKind,item})=>{
      if(kind!=='all'&&kind!==entryKind)return false;
      const entryStatus=item.status||item.review_status;
      if(status!=='all'&&status!==entryStatus)return false;
      if(!needle)return true;
      const haystack=[item.id,item.name,item.description,item.category,item.license,item.rule_system,...(item.authors||[]),...(item.tags||[]),...(item.capabilities||[]),...(item.requires||[]),...(item.provides||[]),...(item.uses||[])].join(' ').toLocaleLowerCase();
      return haystack.includes(needle);
    }).sort((a,b)=>(a.item.name||a.item.id).localeCompare(b.item.name||b.item.id,'zh-CN'));
  },[index,kind,query,status]);
  const statuses=useMemo(()=>[...new Set([...(index?.preset_library||[]).map(item=>item.status),...(index?.plugins||[]).map(item=>item.review_status)].filter(Boolean))].sort(),[index]);
  return <section className="registry-explorer">
    <div className="section-title"><div><span className="eyebrow">FIND. CHECK. THEN CHOOSE.</span><h2><ShieldCheck size={20}/>作品目录与兼容信息</h2></div><Button className="outline compact" icon={RefreshCw} disabled={busy} onClick={load}>刷新目录</Button></div>
    <p className="registry-notice">{payload?.notice||'本地基础目录只提供可审阅元数据，不会自动安装代码。'} {index?.github_repository&&<span>来源仓库：{index.github_repository}</span>}</p>
    {error&&<div className="registry-error" role="alert"><AlertCircle size={17}/><span>{error}</span><Button className="ghost compact" disabled={busy} onClick={load}>重试</Button></div>}
    <div className="registry-filters"><label><Search size={16}/><input aria-label="搜索目录作品" value={query} onChange={event=>setQuery(event.target.value)} placeholder="搜索名称、作者、规则或能力"/></label><select aria-label="目录作品类型" value={kind} onChange={event=>setKind(event.target.value)}><option value="all">全部类型</option><option value="preset">玩法预设</option><option value="plugin">代码模块</option></select><select aria-label="目录审核状态" value={status} onChange={event=>setStatus(event.target.value)}><option value="all">全部状态</option>{statuses.map(value=><option value={value} key={value}>{STATUS[value]?.label||value}</option>)}</select></div>
    {index&&<p className="registry-count">目录收录 {index.preset_library.length} 个预设、{index.plugins.length} 个模块 · 当前显示 {entries.length} 项</p>}
    {busy&&!index&&<p className="registry-empty">正在读取本地目录…</p>}
    {index&&entries.length>0&&<div className="registry-grid">{entries.map(({kind:itemKind,item})=><CatalogCard key={itemKind+':'+item.id+'@'+item.version} kind={itemKind} item={item} compatibility={payload?.compatibility?.[itemKind==='preset'?'presets':'plugins']?.[`${item.id}@${item.version}`]} currentHost={payload?.compatibility?.host_version}/>)}</div>}
    {index&&entries.length===0&&<p className="registry-empty">没有符合筛选条件的作品。试试清除搜索或筛选项。</p>}
    <p className="registry-integrity-note">目录状态不是代码安全审计。SHA-256 只用于校验字节；公开下载前仍需核对授权、来源、签名与版本。旧房间不会随目录更新而改变。</p>
  </section>;
}
