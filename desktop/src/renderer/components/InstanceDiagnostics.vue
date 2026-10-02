<script setup lang="ts">
import {ref} from 'vue';
import {Check,TriangleAlert,RefreshCw,ShieldCheck} from 'lucide-vue-next';
import {invoke} from '../bridge';
import type {Diagnostic} from '../../types';
const props=defineProps<{instanceId:string}>();
const checks=ref<Diagnostic[]>([]);const busy=ref(false);const error=ref('');
async function run(){
  busy.value=true;error.value='';
  try{checks.value=await invoke<Diagnostic[]>('diagnostics',{instanceId:props.instanceId});}
  catch(value:any){error.value=value.message;}
  finally{busy.value=false;}
}
</script>
<template>
  <section class="panel diagnostics-panel">
    <div class="panel-title"><h3><ShieldCheck :size="18"/>开桌自检</h3><button class="secondary" :disabled="busy" @click="run"><RefreshCw :size="15" :class="{spin:busy}"/>{{busy?'检查中…':'运行本机自检'}}</button></div>
    <p class="help-text">只检查本机状态、配置标志和游戏健康接口。不会调用外部模型、测试余额、生成声音或自动调整防火墙；“有网卡”不等于同伴已连通。</p>
    <p v-if="error" class="warning" role="alert">{{error}}</p>
    <ul v-if="checks.length" class="diagnostic-list">
      <li v-for="check in checks" :key="check.id" :data-status="check.status"><component :is="check.status==='passed'?Check:TriangleAlert" :size="17"/><div><b>{{check.label}}</b><p>{{check.detail}}</p></div></li>
    </ul>
  </section>
</template>
