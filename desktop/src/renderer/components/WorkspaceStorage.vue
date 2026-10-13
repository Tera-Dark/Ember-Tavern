<script setup lang="ts">
import {ref,onMounted} from 'vue';
import {FolderOpen} from 'lucide-vue-next';
import {invoke} from '../bridge';
import {useDesktop} from '../useDesktop';
const d=useDesktop();const location=ref<{root:string;defaultRoot:string;custom:boolean;minimumDesktop:string}|null>(null),pending=ref(false),error=ref('');
onMounted(async()=>{try{location.value=await invoke('workspaceLocation');}catch(e:any){error.value=e.message;}});
async function choose(action:'choose'|'default'){if(pending.value)return;pending.value=true;error.value='';try{const result=await invoke('chooseWorkspaceLocation',{action});if(result.unchanged)d.flash('已在使用这个工作区。');}catch(e:any){error.value=e.message;}finally{pending.value=false;}}
</script>
<template><section class="panel workspace-storage"><div class="panel-title"><h3><FolderOpen :size="18"/>整个桌面工作区</h3><span class="badge">{{location?.custom?'自定义目录':'默认目录'}}</span></div><p class="help-text">酒馆环境、存档、备份和加密连接档案统一保存在这里。选择空目录可创建新工作区，选择已有余烬工作区可重新打开。</p><code class="storage-path">{{location?.root||d.state.value.root}}</code><p v-if="error" class="warning" role="alert">{{error}}</p><p class="help-text">切换时会停止所有酒馆并重新打开桌面，同伴会暂时断线。原目录保留，目录之间不会自动移动或合并。重新选择原目录即可继续原来的冒险。</p><p v-if="location?.custom" class="help-text">早于 {{location.minimumDesktop}} 的桌面只能读取默认目录。降级前请先切回默认工作区；手动安装旧版本也不会迁移此目录。</p><div class="row"><button class="secondary" :disabled="pending||!location||d.state.value.tasks.some(t=>t.status==='running')" @click="choose('choose')"><FolderOpen :size="16"/>{{pending?'等待目录确认…':'选择工作区目录'}}</button><button v-if="location?.custom" class="text-button" :disabled="pending||d.state.value.tasks.some(t=>t.status==='running')" @click="choose('default')">切回默认工作区</button></div></section></template>
