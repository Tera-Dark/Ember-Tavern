<script setup lang="ts">
import {computed,ref} from 'vue';
import {Flame,Plus,Search,Monitor,Play,ArrowUpRight,Star,MoreHorizontal,LoaderCircle,FolderOpen,Settings2,Users,History} from 'lucide-vue-next';
import {useDesktop} from '../useDesktop';
import {orderInstances} from '../preferences';
const d=useDesktop();const {state,preferences,search,statusLabel,launching}=d;
const filter=ref('all'),menu=ref<string|null>(null);
const instances=computed(()=>orderInstances(state.value.instances,preferences.value).filter(i=>i.name.toLowerCase().includes(search.value.toLowerCase())
 &&(filter.value==='all'||filter.value==='running'&&i.status==='running'||filter.value==='favorite'&&preferences.value.instances[i.id]?.favorite)));
function label(instance:any){if(launching.value.has(instance.id))return '正在准备…';if(instance.status==='busy')return '查看进度';if(instance.status==='error')return '处理问题';if(!instance.commit)return '安装并开桌';return preferences.value.instances[instance.id]?.roomId?'继续冒险':instance.status==='running'?'进入酒馆':'启动并进入';}
</script>
<template>
 <main class="home dashboard">
  <section :class="['dashboard-hero',{'returning':state.instances.length>0}]"><div class="hero-brand"><span class="ember-emblem"><Flame :size="38" :stroke-width="1.5"/></span><h1>余烬<span>酒馆</span></h1><small>EMBER TAVERN</small></div><p>{{state.instances.length?'下一场冒险，接着从这里开始。':'准备一间酒馆，邀请同伴打开一个世界。'}}</p></section>
  <label class="dashboard-search"><Search :size="21"/><input v-model="search" placeholder="搜索你的酒馆…" aria-label="搜索实例"/><span>本机工作区</span></label>
  <div class="dashboard-heading"><div class="filter-tabs" aria-label="实例筛选"><button :class="{active:filter==='all'}" @click="filter='all'">所有酒馆 <small>{{state.instances.length}}</small></button><button :class="{active:filter==='running'}" @click="filter='running'">运行中</button><button :class="{active:filter==='favorite'}" @click="filter='favorite'"><Star :size="14"/>收藏</button></div><button class="text-button" @click="d.refresh()">刷新状态</button></div>
  <section class="instance-grid">
   <button class="instance-card new-card" @click="d.modal.value='create'"><span class="new-symbol"><Plus :size="28"/></span><div><h2>新建酒馆实例</h2><p>独立环境，自动准备。<br/>先开一桌，无需模型密钥。</p></div><span class="card-link">创建你的下一场冒险 <ArrowUpRight :size="16"/></span></button>
   <article v-for="instance in instances" :key="instance.id" :class="['instance-card',{'is-running':instance.status==='running'}]">
    <div class="card-top"><span class="instance-symbol"><Monitor :size="23"/></span><div class="card-tools"><button :aria-label="(preferences.instances[instance.id]?.favorite?'取消收藏 ':'收藏 ')+instance.name" :class="{favorited:preferences.instances[instance.id]?.favorite}" @click="d.favorite(instance.id)"><Star :size="16"/></button><button :aria-label="'更多操作 '+instance.name" :aria-expanded="menu===instance.id" @click="menu=menu===instance.id?null:instance.id"><MoreHorizontal :size="21"/></button></div></div>
    <button class="card-name" @click="d.enter(instance)"><h2>{{instance.name}}</h2></button>
    <span :class="['status',instance.status]"><i/>{{statusLabel[instance.status]||'正在同步'}}</span>
    <p class="card-description">{{preferences.instances[instance.id]?.roomTitle||'房间与进度保存在这间酒馆'}}<br/><span>{{instance.version||'随桌面提供的兼容本体'}} · {{instance.lan?'同伴可通过 LAN 入座':'仅本机'}}</span></p>
    <div v-if="instance.task" class="card-task"><span>{{instance.task.stage}}</span><span>{{instance.task.percent}}%</span><progress :value="instance.task.percent" max="100"/></div>
    <button class="card-launch" :disabled="launching.has(instance.id)" @click="d.launch(instance)"><LoaderCircle v-if="launching.has(instance.id)" class="spin" :size="17"/><Play v-else :size="15"/>{{label(instance)}}<ArrowUpRight :size="16"/></button>
    <div v-if="menu===instance.id" class="card-menu"><button @click="menu=null;d.enter(instance)"><Settings2 :size="16"/>管理酒馆</button><button @click="menu=null;d.enter(instance,'setup')"><Users :size="16"/>选择冒险与邀请同伴</button><button @click="menu=null;d.enter(instance);d.versionsOpen.value=true"><History :size="16"/>版本与恢复</button><button @click="menu=null;d.act('instanceAction',{instanceId:instance.id,action:'folder'})"><FolderOpen :size="16"/>打开数据目录</button></div>
   </article>
  </section>
  <div v-if="state.instances.length&&!instances.length" class="empty search-empty"><Search :size="25"/><h3>没有找到匹配的酒馆</h3><p>试试其他名称，或切换回所有酒馆。</p><button class="secondary" @click="search='';filter='all'">清除筛选</button></div>
  <section class="dashboard-tip"><Users :size="21"/><div><b>一位房主，一桌同伴。</b><p>只有房主安装桌面，同伴通过浏览器入座。默认演示开桌无需 API Key。</p></div><span>数据留在你的电脑</span></section>
 </main>
</template>
