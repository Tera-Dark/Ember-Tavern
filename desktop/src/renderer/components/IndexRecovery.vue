<script setup lang="ts">
import {ref} from 'vue';
import {TriangleAlert,ShieldCheck,FolderOpen} from 'lucide-vue-next';
import {invoke} from '../bridge';
import type {IndexRecovery,IndexIssue,Instance} from '../../types';
defineProps<{report:IndexRecovery;root:string}>();
const emit=defineEmits<{restored:[value:Instance];error:[message:string]}>();
const busy=ref('');
async function recover(entry:IndexIssue){
  if(!confirm('请先关闭旧启动器及其酒馆服务。恢复会复制数据和受支持的配置，保留原目录，重新安装本体。原房主身份需要原 Windows 用户的 desktop-credentials.json；不会重置账号。确认已停止旧服务？'))return;
  busy.value=entry.entry_id;
  try{emit('restored',await invoke<Instance>('recoverIndex',{entryId:entry.entry_id,confirmStopped:true}));}
  catch(error:any){emit('error',error.message);}
  finally{busy.value='';}
}
</script>
<template>
  <details v-if="report.entries.length" class="panel recovery-panel" :open="report.pending>0">
    <summary><TriangleAlert :size="18"/>旧实例诊断 · {{report.pending}} 条待处理<span>原记录不会静默丢弃</span></summary>
    <p class="help-text">有效实例仍可使用。首次修改索引前，会在本机 index-backups 保存原始索引；隔离记录在保存、重启后继续保留。不会删除旧目录。</p>
    <p v-if="report.backup_name" class="help-text"><ShieldCheck :size="14"/>原索引备份：<code>{{root}} / index-backups / {{report.backup_name}}</code></p>
    <article v-for="entry in report.entries" :key="entry.entry_id" class="recovery-row">
      <div><b>{{entry.name||'未命名旧记录'}}</b><code>{{entry.legacy_id||'无有效 ID'}}</code><p>{{entry.restored_id?'已恢复到新安全 ID，原目录保留。':entry.reason}}</p>
        <small v-if="!entry.can_recover&&!entry.restored_id">不满足自动恢复条件：可能是路径不安全、元数据无效、目录缺失／链接或重复使用。请按文档人工检查，不能直接删除旧数据。</small>
      </div>
      <button v-if="entry.can_recover" class="secondary" :disabled="!!busy" @click="recover(entry)"><FolderOpen :size="15"/>{{busy===entry.entry_id?'正在安全复制…':'复制恢复'}}</button>
      <span v-else-if="entry.restored_id" class="status ready">已恢复</span>
    </article>
  </details>
</template>
