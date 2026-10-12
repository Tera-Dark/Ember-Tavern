import {computed,ref,inject,type InjectionKey} from 'vue';
import {Monitor,BookOpen,Users,Blocks,Settings2,ScrollText} from 'lucide-vue-next';
import {invoke} from './bridge';
import {loadPreferences,savePreferences,lastRoom,chooseContinuation} from './preferences';
import type {UIPreferences} from './preferences';
import type {Instance,State,Room,Invite,Theme,RPCMethod} from '../types';
function storedTheme(){try{return localStorage.getItem('ember-desktop-theme');}catch{return null;}}
export function createDesktop(){
 const preferences=ref<UIPreferences>(loadPreferences()),page=ref<'home'|'tasks'|'content'|'settings'>('home');
 const shareAddresses=ref<Record<string,string>>({});
 const operationCounts=new Map<string,number>();
 const desktopPrefs=ref({closeBehavior:'ask',openBehavior:'dashboard',readOnly:false,error:undefined as string|undefined});
 const busyIds=ref(new Set<string>()),launching=ref(new Set<string>()),connectionError=ref(''),lastSync=ref(0);
const native=window.emberDesktop?.kind==='native';
const versionsOpen=ref(false);
const state=ref<State>({launcher_version:'0.2.0-beta.4',root:'',platform:'Windows x64',instances:[],tasks:[]});
const search=ref('');const selected=ref<string|null>(null);const tab=ref('overview');const modal=ref<'create'|'invite'|null>(null);const loading=ref(false);const error=ref('');const toast=ref('');
const rooms=ref<Room[]>([]);const room=ref<Room|null>(null);const guests=ref<Invite[]>([]);const logs=ref<string[]>([]);const settings=ref<Record<string,any>>({});const changes=ref<Record<string,string>>({});
const theme=ref<Theme>((['ember','moonlit','light'].includes(storedTheme()||'')?storedTheme():'ember') as Theme);
const create=ref({name:'我的余烬酒馆',port:'' as number|string,lan:true});const roomTitle=ref('');const identity=ref('');const issued=ref<Invite|null>(null);const connection=ref({name:'',port:8180,lan:true,channel:'bundled'});
let firstRun:{instanceId:string;epoch:number}|undefined;let timer:ReturnType<typeof setTimeout>;let disposed=false;let workspaceEpoch=0;let roomEpoch=0;let refreshPending:Promise<void>|undefined;let toastTimer:ReturnType<typeof setTimeout>;
const active=computed(()=>state.value.instances.find(item=>item.id===selected.value));const filtered=computed(()=>state.value.instances.filter(item=>item.name.toLowerCase().includes(search.value.toLowerCase())));
const busy=computed(()=>!!selected.value&&(busyIds.value.has(selected.value)||launching.value.has(selected.value))||active.value?.status==='busy');const running=computed(()=>active.value?.status==='running');
const statusLabel:Record<string,string>={running:'运行中',ready:'已安装 · 待启动',not_installed:'待安装',busy:'任务进行中',error:'需要关注'};
const tabs=[{id:'setup',name:'开桌向导',icon:BookOpen},{id:'overview',name:'实例概览',icon:Monitor},{id:'rooms',name:'房间与同伴',icon:Users},{id:'plugins',name:'插件管理',icon:Blocks},{id:'settings',name:'API 与配置',icon:Settings2},{id:'logs',name:'运行日志',icon:ScrollText}];
const settingGroups=[{title:'世界知识 · Gemini',note:'可选高级知识顾问，仅真实双模型模式需要；单模型无需 Gemini。',fields:[['GEMINI_API_KEY','API Key','password'],['GEMINI_MODEL','模型','text']]},{title:'决策模型 · OpenAI-compatible',note:'单模型开桌只需这组配置；高级双模型再添加 Gemini。保存不代表密钥、余额或联网已验证。',fields:[['DECISION_API_KEY','API Key','password'],['DECISION_BASE_URL','接口地址','url'],['DECISION_MODEL','模型','text']]},{title:'服务端 TTS',note:'浏览器朗读不需要此配置；服务端生成可能收费。',fields:[['TTS_API_KEY','API Key','password'],['TTS_BASE_URL','接口地址','url'],['TTS_MODEL','模型','text'],['TTS_VOICE','声音 ID','text']]}];
function flash(value:string){toast.value=value;clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.value='',5000);}
function setTheme(value:Theme){theme.value=value;document.documentElement.dataset.theme=value;try{localStorage.setItem('ember-desktop-theme',value);}catch{}}
async function refresh():Promise<void>{
 if(refreshPending)return refreshPending;
 refreshPending=(async()=>{try{const next=await invoke<State>('state');if(!disposed){state.value=next;connectionError.value='';lastSync.value=Date.now();if(firstRun&&next.instances.find(i=>i.id===firstRun!.instanceId)?.status==='running'){const target=firstRun;firstRun=undefined;if(selected.value===target.instanceId&&workspaceEpoch===target.epoch&&tab.value==='overview'){tab.value='setup';void loadRooms();}}}}catch(e:any){if(!disposed)connectionError.value=e.message;}finally{refreshPending=undefined;}})();return refreshPending;
}
async function act(method:RPCMethod,args:Record<string,any>={}){
 const target=args.instanceId||selected.value;const epoch=workspaceEpoch;
 if(target){operationCounts.set(target,(operationCounts.get(target)||0)+1);busyIds.value=new Set(operationCounts.keys());}else loading.value=true;
 error.value='';
 try{const result=await invoke(method,{instanceId:target,...args});await refresh();return epoch===workspaceEpoch||args.instanceId||method==='createInstance'?result:null;}
 catch(e:any){error.value=e.message;return null;}
 finally{if(target){const count=(operationCounts.get(target)||1)-1;if(count)operationCounts.set(target,count);else operationCounts.delete(target);busyIds.value=new Set(operationCounts.keys());}else loading.value=false;}
}
async function enter(instance:Instance,requestedTab?:string){
 workspaceEpoch++;roomEpoch++;selected.value=instance.id;page.value='home';tab.value=requestedTab||(lastRoom(preferences.value,instance.id)?'overview':'setup');room.value=null;guests.value=[];rooms.value=[];
 connection.value={name:instance.name,port:instance.port,lan:instance.lan,channel:instance.channel};
 if(instance.status==='running')await loadRooms();
 void invoke('instanceAction',{instanceId:instance.id,action:'check'}).then(refresh).catch(()=>{});
}
async function loadRooms(){const target=selected.value,epoch=workspaceEpoch,intent=roomEpoch;if(!target)return;
 try{const value=await invoke<Room[]>('rooms',{instanceId:target});if(epoch!==workspaceEpoch||intent!==roomEpoch||selected.value!==target)return;rooms.value=value.filter(item=>item.is_owner);
 const choice=chooseContinuation(rooms.value,room.value?.id||lastRoom(preferences.value,target));if(choice.room)await selectRoom(choice.room.id);
 }catch(e:any){if(epoch===workspaceEpoch)error.value=e.message;}
}
async function selectRoom(roomId:string){const target=selected.value,epoch=++roomEpoch,workspace=workspaceEpoch;if(!target)return;
 try{const [value,invites]=await Promise.all([invoke<Room>('room',{instanceId:target,roomId}),invoke<Invite[]>('guestInvites',{instanceId:target,roomId})]);
 if(epoch!==roomEpoch||workspace!==workspaceEpoch||selected.value!==target)return;room.value=value;guests.value=invites;rememberRoom(target,value);
 }catch(e:any){if(epoch===roomEpoch)error.value=e.message;}
}
async function switchTab(value:string){tab.value=value;if((value==='rooms'||value==='plugins')&&running.value)await loadRooms();if(value==='settings'){const value=await act('settings');if(value){settings.value=value;changes.value={};}}if(value==='logs'){const latest=await invoke('state');logs.value=latest.tasks.filter((item:any)=>item.instance_id===selected.value).flatMap((item:any)=>item.logs||[]).slice(-160);}}
async function action(name:string){const result=await act('instanceAction',{action:name});if(result&&name==='check')flash('GitHub 最新本体：'+result.version);if(result&&name==='update')flash('正在更新至 GitHub 最新本体；数据会先备份。');}
async function createInstance(){loading.value=true;try{const result=await act('createInstance',create.value);if(result){modal.value=null;const current=state.value.instances.find(i=>i.id===result.instance.id)||result.instance;await enter(current,current.status==='running'?'setup':'overview');if(current.status!=='running')firstRun={instanceId:current.id,epoch:workspaceEpoch};flash('正在准备酒馆，进度可在任务中心查看。');}}finally{loading.value=false;}}
async function newRoom(){roomEpoch++;const result=await act('createRoom',{title:roomTitle.value||'我们的第一夜'});if(result){roomTitle.value='';await loadRooms();await selectRoom(result.id);flash('房间已创建。下一步为同伴创建身份密钥。');}}
async function issue(){if(!room.value||!identity.value.trim())return;const result=await act('issueGuest',{roomId:room.value.id,identity:identity.value});if(result?.invite){issued.value=result.invite;modal.value='invite';identity.value='';await selectRoom(room.value.id);}}
async function revoke(invite:Invite){if(!room.value||!confirm('撤销 '+invite.identity+' 的密钥并移除入座？'))return;const result=await act('revokeGuest',{roomId:room.value.id,inviteId:invite.id});if(result){await selectRoom(room.value.id);flash('密钥已撤销，连接和角色分配已解除。');}}
async function toggle(plugin:any){if(!room.value)return;const intent=++roomEpoch;const result=await act('roomAction',{roomId:room.value.id,action:'plugin',pluginId:plugin.id,enabled:!plugin.enabled});if(result&&intent===roomEpoch){room.value=result;flash('模块设置已更新，关闭不删除数据。');}}
async function accepting(){if(!room.value)return;const intent=++roomEpoch;const result=await act('roomAction',{roomId:room.value.id,action:'invitation',accepting:room.value.access?.accepting_players===false});if(result&&intent===roomEpoch)room.value=result;}
async function saveSettings(){const result=await act('saveSettings',{values:changes.value});if(result){changes.value={};settings.value=await invoke('settings',{instanceId:selected.value});flash('配置已保存。启动实例后生效；密钥不会回显。');}}
async function saveConnection(){if(await act('configureInstance',connection.value))flash('网络与实例配置已保存。');}
async function copy(text:string){try{if(native)await invoke('clipboard',{text});else await navigator.clipboard.writeText(text);flash('已复制');}catch{flash('自动复制不可用，请选中内容手动复制');}}
async function openRoom(roomId:string){const result=await act('openGame',{roomId});if(result?.url)window.open(result.url,'_blank','noopener');}
async function openGame(){if(room.value)await openRoom(room.value.id);}
async function recovered(instance:Instance){await refresh();await enter(instance);flash('已复制旧数据到新安全实例，原目录保留。请安装本体后继续；不会重置旧账号。');}

function rememberRoom(instanceId:string,value:Room){
 const existing=preferences.value.instances[instanceId]||{favorite:false,lastUsed:0};
 preferences.value.instances[instanceId]={...existing,lastUsed:Date.now(),roomId:value.id,roomTitle:value.title};savePreferences(preferences.value);try{localStorage.setItem('ember-first-table-room-'+instanceId,value.id);}catch{}
}
function rememberSelection(value:Room){workspaceEpoch++;roomEpoch++;room.value=value;guests.value=[];if(selected.value)rememberRoom(selected.value,value);}
function favorite(instanceId:string){const existing=preferences.value.instances[instanceId]||{favorite:false,lastUsed:0};preferences.value.instances[instanceId]={...existing,favorite:!existing.favorite};savePreferences(preferences.value);}
function dismissTask(taskId:string){preferences.value.dismissedTasks=[...preferences.value.dismissedTasks.filter(id=>id!==taskId),taskId].slice(-100);savePreferences(preferences.value);}
async function launch(instance:Instance){
 if(launching.value.has(instance.id))return;
 if(instance.status==='busy'){await enter(instance,'overview');return;}
 if(instance.status==='error'){await enter(instance,'overview');return;}
 launching.value=new Set([...launching.value,instance.id]);
 const token=++workspaceEpoch;selected.value=instance.id;page.value='home';tab.value='overview';room.value=null;rooms.value=[];guests.value=[];
 connection.value={name:instance.name,port:instance.port,lan:instance.lan,channel:instance.channel};
 try{
  let task:any;
  if(instance.status!=='running')task=await invoke('instanceAction',{instanceId:instance.id,action:instance.commit?'start':'install'});
  const deadline=Date.now()+30*60*1000;
  while(!disposed){
   await refresh();const current=state.value.instances.find(i=>i.id===instance.id);const finished=task?.id&&state.value.tasks.find(t=>t.id===task.id);
   if(finished?.status==='failed')throw new Error(finished.error||'酒馆未能启动，请查看任务中心');
   if(!current)throw new Error('酒馆已不在当前索引，请刷新');
   if(current.status==='running')break;
   if(Date.now()>deadline)throw new Error('准备时间较长，可在任务中心继续查看；没有重置数据');
   await new Promise(resolve=>setTimeout(resolve,1000));
  }
  if(disposed||token!==workspaceEpoch||selected.value!==instance.id){flash('酒馆已准备好，可从首页继续。');return;}
  const list=await invoke<Room[]>('rooms',{instanceId:instance.id});
  if(disposed||token!==workspaceEpoch||selected.value!==instance.id)return;
  rooms.value=list.filter(r=>r.is_owner);
  const choice=chooseContinuation(list,lastRoom(preferences.value,instance.id));
  if(choice.room){await selectRoom(choice.room.id);if(token===workspaceEpoch&&selected.value===instance.id)await openRoom(choice.room.id);}
  else{tab.value='setup';if(choice.missing)flash('上次冒险不在当前列表，请明确选择要继续的房间。');else if(choice.needsSelection)flash('这间酒馆有多场冒险，请选择要继续的一场。');}
 }catch(e:any){error.value=e.message;}
 finally{const next=new Set(launching.value);next.delete(instance.id);launching.value=next;}
}
function navigate(value:'home'|'tasks'|'content'|'settings'){workspaceEpoch++;roomEpoch++;selected.value=null;page.value=value;room.value=null;guests.value=[];}
function inspectTask(instanceId:string){const instance=state.value.instances.find(i=>i.id===instanceId);if(instance)void enter(instance,'overview');}
async function poll(){await refresh();if(!disposed)timer=setTimeout(poll,document.hidden?8000:1800);}
async function saveDesktopPrefs(){try{desktopPrefs.value=await invoke('saveDesktopPreferences',{closeBehavior:desktopPrefs.value.closeBehavior,openBehavior:desktopPrefs.value.openBehavior});flash('桌面使用习惯已保存。');}catch(e:any){error.value=e.message;}}
async function initializePreferences(){if(!native)return;const epoch=workspaceEpoch;try{desktopPrefs.value=await invoke('desktopPreferences');if(desktopPrefs.value.openBehavior==='last'){await refresh();if(epoch!==workspaceEpoch||selected.value||page.value!=='home')return;const last=[...state.value.instances].sort((a,b)=>(preferences.value.instances[b.id]?.lastUsed||0)-(preferences.value.instances[a.id]?.lastUsed||0))[0];if(last&&preferences.value.instances[last.id]?.lastUsed)void launch(last);}}catch(e:any){error.value='桌面偏好暂时不可用：'+e.message;}}
function start(){disposed=false;setTheme(theme.value);void poll();void initializePreferences();}
function stop(){disposed=true;workspaceEpoch++;roomEpoch++;clearTimeout(timer);clearTimeout(toastTimer);}
return {native,state,preferences,shareAddresses,desktopPrefs,saveDesktopPrefs,page,search,selected,tab,modal,loading,error,connectionError,lastSync,toast,theme,versionsOpen,active,busy,running,tabs,statusLabel,rooms,room,guests,logs,settings,changes,create,roomTitle,identity,issued,connection,settingGroups,busyIds,launching,flash,setTheme,refresh,act,enter,loadRooms,selectRoom,switchTab,action,createInstance,newRoom,issue,revoke,toggle,accepting,saveSettings,saveConnection,copy,openRoom,openGame,recovered,rememberSelection,rememberRoom,favorite,dismissTask,launch,navigate,inspectTask,start,stop};
}
export type DesktopStore=ReturnType<typeof createDesktop>;
export const desktopKey:InjectionKey<DesktopStore>=Symbol('desktop');
export function useDesktop():DesktopStore{const value=inject(desktopKey);if(!value)throw new Error('Desktop workspace unavailable');return value;}
