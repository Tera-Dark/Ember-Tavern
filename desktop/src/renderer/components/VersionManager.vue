<script setup lang="ts">
import {computed,onMounted,onUnmounted,ref,nextTick} from 'vue';
import {Download,RefreshCw,ArrowLeft,History,TriangleAlert,Check,X} from 'lucide-vue-next';
import SnapshotManager from './SnapshotManager.vue';
import {invoke} from '../bridge';
import {useDesktop} from '../useDesktop';
import {trapModalFocus} from '../modalFocus';
import type {DesktopUpdateState,Instance} from '../../types';
const d=useDesktop(),confirmation=ref<{kind:'desktop'|'host';tag?:string}|null>(null),impactDialog=ref<HTMLElement|null>(null);let releaseFocus:(()=>void)|undefined;
const affected=computed(()=>confirmation.value?.kind==='desktop'?d.state.value.instances.filter(i=>i.status==='running'):props.instance?.status==='running'?[props.instance]:[]);
const props=defineProps<{updates?:DesktopUpdateState;instance?:Instance}>();
const emit=defineEmits<{close:[];refresh:[]}>();
const previewing=ref(false);
const loading=ref(false),error=ref(''),message=ref('');
const selectedDesktop=ref(''),selectedHost=ref('');
const hosts=ref<{tag:string;version:string;published_at:string}[]>([]);
const working=computed(()=>previewing.value||loading.value||['checking','downloading','ready','installing'].includes(props.updates?.phase||'')||props.instance?.status==='busy');
const selectedRelease=computed(()=>props.updates?.releases.find(x=>x.tag===selectedDesktop.value));
async function check(){
 loading.value=true;error.value='';
 try{
  if(window.emberDesktop?.kind==='native')await invoke('desktopUpdateCheck');
  hosts.value=await invoke('instanceVersions');
  if(props.instance)await invoke('instanceAction',{instanceId:props.instance.id,action:'check'});
 }catch(e:any){error.value=e.message;}finally{loading.value=false;emit('refresh');}
}
async function applyDesktop(tag:string){
 loading.value=true;error.value='';message.value='';
 try{await invoke('desktopUpdateInstall',{tag});message.value='正在下载并校验安装包。完成后会停止实例、安装并重新打开桌面。';}
 catch(e:any){error.value=e.message;}finally{loading.value=false;emit('refresh');}
}
async function applyHost(tag?:string){
 if(!props.instance)return;
 loading.value=true;error.value='';message.value='';
 try{
  if(tag)await invoke('switchInstanceVersion',{instanceId:props.instance.id,tag});
  else await invoke('instanceAction',{instanceId:props.instance.id,action:'update'});
  message.value='版本任务已开始，可在实例卡片查看进度。运行中的实例会自动停止并恢复启动。';
 }catch(e:any){error.value=e.message;}finally{loading.value=false;emit('refresh');}
}
async function preview(kind:'desktop'|'host',tag?:string){if(previewing.value||confirmation.value)return;previewing.value=true;try{await d.refresh();confirmation.value={kind,tag};await nextTick();if(impactDialog.value)releaseFocus=trapModalFocus(impactDialog.value,closePreview);}finally{previewing.value=false;}}
function closePreview(){if(loading.value)return;releaseFocus?.();releaseFocus=undefined;confirmation.value=null;}
function desktop(tag:string){void preview('desktop',tag);}
function host(tag?:string){void preview('host',tag);}
async function confirmApply(){const action=confirmation.value;if(!action)return;releaseFocus?.();releaseFocus=undefined;confirmation.value=null;if(action.kind==='desktop')await applyDesktop(action.tag!);else await applyHost(action.tag);}
onUnmounted(()=>releaseFocus?.());
onMounted(check);
</script>

<template>
 <main class="version-manager home">
  <div class="row"><button class="text-button" @click="emit('close')"><ArrowLeft :size="16"/>返回控制台</button><button class="secondary" :disabled="working" @click="check"><RefreshCw :size="16"/>检查 GitHub 更新</button></div>
  <section class="welcome"><span class="eyebrow">KEEP YOUR TAVERN WITH YOU</span><h1>更新与版本</h1><p>旧安装包也能发现新的发行版。你决定何时更新，也可以回到先前的版本。</p></section>
  <div v-if="error||updates?.error" class="error-banner" role="alert"><TriangleAlert :size="17"/>{{error||updates?.error}}</div>
  <div v-if="message" class="notice" role="status"><Check :size="17"/><p>{{message}}</p></div>
  <section class="panel">
   <div class="panel-title"><h2><Download :size="20"/>余烬桌面</h2><span class="muted">当前 {{updates?.current||'开发预览'}}</span></div>
   <template v-if="updates">
    <div v-if="updates.available" class="notice"><Download :size="18"/><p>发现新版 {{updates.latest?.version}}</p><button class="primary" :disabled="working||!updates.can_install||!updates.latest?.installable" @click="desktop(updates.latest!.tag)">立即更新</button></div>
    <p v-else-if="updates.suppressed" class="help-text">已保留你选择的旧版，{{updates.latest?.version}} 的更新提示已消除。仍可手动更新；发布更高版本时会重新提示。</p>
    <p v-else class="help-text">{{updates.phase==='checking'?'正在读取 GitHub 发行目录…':updates.checked_at?'已检查发行目录。':'尚未检查更新。'}}</p>
    <div v-if="['downloading','ready','installing'].includes(updates.phase)" class="notice" role="status"><p>{{updates.phase==='downloading'?'下载安装包':updates.phase==='ready'?'校验完成，准备安装':'正在安装并重启'}} · {{updates.target}} · {{updates.percent}}%</p><progress :value="updates.percent" max="100"/></div>
    <div class="form"><label>切换桌面版本<select v-model="selectedDesktop" :disabled="working"><option value="">选择 GitHub 已发布版本</option><option v-for="release in updates.releases" :key="release.tag" :value="release.tag" :disabled="!release.installable||release.version===updates.current">{{release.version}}{{release.prerelease?' · 测试版':''}}{{!release.installable?' · 缺少安装文件':''}}{{release.version===updates.current?' · 当前版本':''}}</option></select></label><button class="secondary" :disabled="working||!updates.can_install||!selectedRelease?.installable" @click="desktop(selectedDesktop)"><History :size="16"/>安装所选版本并重启</button></div>
    <p v-if="selectedRelease?.reason" class="help-text">{{selectedRelease.reason}}</p>
    <pre v-if="selectedRelease?.notes" class="release-notes">{{selectedRelease.notes}}</pre>
    <p v-if="!updates.can_install" class="help-text">下载和安装仅在 Windows 正式桌面包中可用。</p>
   </template>
   <p class="help-text">切换桌面保留实例、账号与配置。回退后，同一个新版不再自动提示。早期未包含更新底座的桌面包需要先升级一次。</p>
  </section>
  <section v-if="instance" class="panel">
   <div class="panel-title"><h2><History :size="20"/>{{instance.name}} · 游戏本体</h2><span class="muted">当前 {{instance.version||'尚未安装'}}</span></div>
   <div v-if="instance.update?.available" class="notice"><p>发现新版 {{instance.update.latest?.version}}（{{instance.update.latest?.tag}}）</p><button class="primary" :disabled="working||!instance.commit" @click="host()">更新本体</button></div>
   <p v-if="instance.update?.suppressed" class="help-text">已回退并消除当前新版的提示，可随时手动切换。</p>
   <p v-if="instance.update?.error" class="warning">{{instance.update.error}}</p>
   <div class="form"><label>切换游戏本体<select aria-label="切换游戏本体" v-model="selectedHost" :disabled="working"><option value="">选择已发布版本</option><option v-for="release in hosts" :key="release.tag" :value="release.tag">{{release.tag}}</option></select></label><button class="secondary" :disabled="working||!selectedHost||!instance.commit" @click="host(selectedHost)">应用所选本体版本</button></div>
   <p class="help-text">每次切换先备份并预检。回退优先恢复该版本离开时的数据快照，较新进度保留在版本备份中；没有兼容快照且旧版无法读取现有数据时，切换会失败并保留原版本。实例目录中的 version-data 保存这些快照。</p>
  </section>
  <SnapshotManager v-if="instance" :key="instance.id" :instance="instance"/>
 </main>
 <Teleport to="body"><div v-if="confirmation" class="overlay"><section ref="impactDialog" class="dialog" role="dialog" aria-modal="true" aria-label="版本切换影响预览"><button class="dialog-close" aria-label="关闭版本影响预览" :disabled="loading" @click="closePreview"><X :size="20"/></button><span class="eyebrow">REVIEW THE CHANGE</span><h2>{{confirmation.kind==='desktop'?'切换余烬桌面':'切换游戏本体'}}</h2><p>目标：{{confirmation.tag||instance?.update?.latest?.tag||'GitHub 最新本体'}}</p><p v-if="affected.length" class="warning">以下 {{affected.length}} 间运行中的酒馆会暂时断线：</p><ul v-if="affected.length" class="impact-list"><li v-for="i in affected" :key="i.id">{{i.name}} · 当前 {{i.version}}</li></ul><p v-else class="help-text">当前没有运行中的受影响酒馆，已有进度与配置仍保留。</p><template v-if="confirmation.kind==='desktop'"><p class="help-text">先下载并校验安装包，再停止管理服务并切换桌面。实例本体、规则与房间内容锁保持原状；支持恢复标记的版本会重新启动原运行实例，早期版需人工启动。</p><p class="help-text">建议先确认完整备份。旧版可能不支持加密连接档案，会保留原文件并使用旧格式配置；不要把切换桌面当成切换房间模型。</p></template><template v-else><p class="help-text">准备新环境后先备份、预检，再切换本体与兼容数据；运行实例会停服后恢复。回退优先使用目标版本离开时的快照，较新进度保留在版本备份中。</p><p class="help-text">不能读取数据时保留原版本。世界书 hash、规则版本与插件 pins 不会因为选择发行版本而偷偷重写。</p></template><p class="help-text">请先告知同伴。实际应用前会重新检查任务和版本状态。</p><div class="row"><button class="secondary" @click="closePreview">取消</button><button class="primary" :disabled="working" @click="confirmApply">确认开始版本切换</button></div></section></div></Teleport>
</template>

<style scoped>
.version-manager{max-width:1050px;margin:0 auto;width:100%;overflow:auto}.version-manager .welcome{display:block}.version-manager h2{display:flex;align-items:center;gap:10px}.version-manager .panel{margin:20px 0}.version-manager .notice{flex-wrap:wrap}.version-manager .notice p{flex:1}.version-manager .form{max-width:650px}.release-notes{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;font-size:13px;color:var(--muted);max-height:250px;overflow:auto;padding:14px;background:var(--surface2);border-radius:8px}progress{width:100%;accent-color:var(--accent)}
</style>
