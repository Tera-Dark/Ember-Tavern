<script setup lang="ts">
import {ref} from 'vue';
import {Check,TriangleAlert,RefreshCw,ShieldCheck,Download} from 'lucide-vue-next';
import {invoke} from '../bridge';
import type {Diagnostic} from '../../types';
const native=window.emberDesktop?.kind==='native';
const props=defineProps<{instanceId:string}>();
const saved=ref(false);
const checks=ref<Diagnostic[]>([]);const busy=ref(false);const error=ref('');
async function run(){
  busy.value=true;error.value='';
  try{checks.value=await invoke<Diagnostic[]>('diagnostics',{instanceId:props.instanceId});}
  catch(value:any){error.value=value.message;}
  finally{busy.value=false;}
}
async function exportReport(){busy.value=true;error.value='';saved.value=false;try{const result=await invoke('exportDiagnostics',{instanceId:props.instanceId});saved.value=result.exported===true;}catch(e:any){error.value=e.message;}finally{busy.value=false;}}
</script>
<template>
  <section class="panel diagnostics-panel">
    <div class="panel-title"><h3><ShieldCheck :size="18"/>开桌自检</h3><button class="secondary" :disabled="busy" @click="run"><RefreshCw :size="15" :class="{spin:busy}"/>{{busy?'检查中…':'运行本机自检'}}</button></div>
    <p class="help-text">只检查本机状态、配置标志和游戏健康接口。不会调用外部模型、测试余额、生成声音或自动调整防火墙；“有网卡”不等于同伴已连通。</p>
    <div v-if="native" class="row"><button class="text-button" :disabled="busy" @click="exportReport"><Download :size="15"/>导出安全诊断摘要</button><small class="muted">仅版本、状态与配置标志，不含地址、密钥、房间或日志正文</small></div>
    <p v-if="saved" class="help-text" role="status">诊断摘要已保存。分享前仍可自行查看 JSON 中的版本和状态字段。</p>
    <p v-if="error" class="warning" role="alert">{{error}}</p>
    <ul v-if="checks.length" class="diagnostic-list">
      <li v-for="check in checks" :key="check.id" :data-status="check.status"><component :is="check.status==='passed'?Check:TriangleAlert" :size="17"/><div><b>{{check.label}}</b><p>{{check.detail}}</p></div></li>
    </ul>
  </section>
</template>
