<script setup lang="ts">
import {ref,watch,onUnmounted,computed} from 'vue';
import {BookOpen,Check,RefreshCw,Upload,ShieldCheck} from 'lucide-vue-next';
import {invoke} from '../bridge';
import type {Instance,PresetEntry,Room} from '../../types';
const props=defineProps<{instance:Instance;native:boolean}>();
const emit=defineEmits<{created:[room:Room];error:[message:string];message:[message:string]}>();
const entries=ref<PresetEntry[]>([]),selected=ref(''),title=ref('我们的新冒险'),hostPlays=ref(true),busy=ref(false),error=ref('');
const chosen=computed(()=>entries.value.find(entry=>entry.package_hash===selected.value));
const labels:Record<string,string>={investigation:'合作调查',adventure:'奇幻探索','slice-of-life':'日常与群像'};
let disposed=false;let intent:{fingerprint:string;key:string}|null=null;
async function load(){if(props.instance.status!=='running')return;try{const result=await invoke<{entries:PresetEntry[]}>('presetCatalog',{instanceId:props.instance.id});if(!disposed){entries.value=result.entries;error.value='';}}catch(value:any){if(!disposed)error.value='玩法库未就绪：'+value.message+'。可使用下方旧入门世界；升级支持 M1 的宿主后刷新。';}}
async function create(){if(!chosen.value)return;busy.value=true;error.value='';try{
  const values={packageHash:chosen.value.package_hash,title:title.value.trim(),hostPlays:hostPlays.value};
  const fingerprint=JSON.stringify(values);if(intent?.fingerprint!==fingerprint)intent={fingerprint,key:crypto.randomUUID()};
  const room=await invoke<Room>('createPresetRoom',{instanceId:props.instance.id,...values,requestKey:intent.key});
  intent=null;emit('created',room);emit('message','整套预设已原子开桌，内容与模块版本已锁定；不会覆盖旧冒险。');
}catch(value:any){error.value=value.message;emit('error',value.message);}finally{busy.value=false;}}
async function importData(){busy.value=true;try{const result=await invoke('importPreset',{instanceId:props.instance.id});if(result?.imported){await load();selected.value=result.package_hash;emit('message','已导入数据包；没有安装或授权依赖代码。');}}catch(value:any){error.value=value.message;emit('error',value.message);}finally{busy.value=false;}}
watch(()=>[props.instance.id,props.instance.status],()=>{if(props.instance.status==='running')load();},{immediate:true});
onUnmounted(()=>{disposed=true;});
</script>
<template>
  <section class="panel desktop-preset-library">
    <div class="panel-title"><div><span class="eyebrow">ONE COMPOSITION. A COMPLETE FIRST SESSION.</span><h3><BookOpen :size="19"/>玩法预设库</h3></div><div class="row"><button class="secondary" :disabled="busy" @click="load"><RefreshCw :size="15"/>刷新预设</button><button class="secondary" :disabled="busy||!native" @click="importData"><Upload :size="15"/>导入预设数据包</button></div></div>
    <p class="help-text">世界书＋有限剧本＋角色模板＋已审阅模块。三个原创样板可走到结局；当前仍是轻规则 / 叙事模式，不是完整 D&D 或 SLG。</p>
    <p v-if="error" class="warning" role="alert">{{error}}</p>
    <div class="desktop-preset-grid"><button v-for="entry in entries" :key="entry.package_hash" :class="['desktop-preset-card',{selected:selected===entry.package_hash}]" @click="selected=entry.package_hash;title=entry.name"><span class="eyebrow">{{labels[entry.play_mode]||'待检查作品'}}</span><Check v-if="selected===entry.package_hash" class="preset-selected" :size="16"/><b>{{entry.name}}</b><small>v{{entry.version}} · {{entry.source==='bundled'?'内置原创样板':'本机作品'}}</small><p>{{entry.description}}</p><span>{{entry.character_count}} 张角色卡 · {{entry.ending_count}} 个结局 · 约 {{entry.duration_minutes}} 分钟</span><strong>{{entry.compatibility.can_create?'依赖满足，可开新桌':'缺少匹配依赖'}}</strong></button></div>
    <div v-if="chosen" class="desktop-preset-chosen"><div class="notice small"><ShieldCheck :size="17"/><p>精确版本 {{chosen.version}} · {{chosen.package_hash.slice(0,16)}}…。默认演示不调用外部主持模型；真实模式 / TTS 等显式生成可能收费。</p></div><p class="help-text">作品许可：{{chosen.license||'未声明'}}。分享前检查各组件授权，本机校验不等于再分发许可。</p><details v-if="chosen.warnings?.length"><summary>作者／许可提醒（{{chosen.warnings.length}}）</summary><p class="help-text" v-for="warning in chosen.warnings" :key="warning">{{warning}}</p></details><p class="warning" v-for="item in chosen.compatibility.blockers" :key="item">无法开桌：{{item}}</p><p class="help-text" v-for="item in chosen.compatibility.warnings" :key="item">可选模块：{{item}}，不会自动下载安装。</p>
      <form class="form" @submit.prevent="create"><label>玩法房间名称<input v-model="title" aria-label="玩法房间名称" maxlength="60" required/></label><label class="checkbox"><input v-model="hostPlays" type="checkbox"/>房主也操控第一位角色（不勾选则全部等待分配）</label><button class="primary" :disabled="busy||!chosen.compatibility.can_create"><BookOpen :size="16"/>{{busy?'整套校验与开桌中…':'用预设开新桌'}}</button></form>
    </div>
    <p v-if="!entries.length&&!error" class="help-text">启动宿主后加载本机作品库。旧房间不自动切换到新的预设版本。</p>
    <p v-if="!native" class="help-text">开发预览不读取本地文件。原生桌面可用安全文件选择器导入 ZIP／JSON；网页创作工坊也支持预览后确认导入。</p>
  </section>
</template>
