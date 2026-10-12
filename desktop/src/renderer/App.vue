<script setup lang="ts">
import {computed,onMounted,onUnmounted,provide} from 'vue';
import {Flame,Download,Home,Library,Activity,Settings2,Bell,X,Minus,Maximize2,ShieldCheck,Check,WifiOff,ArrowRight} from 'lucide-vue-next';
import {invoke} from './bridge';
import {createDesktop,desktopKey} from './useDesktop';
import Dashboard from './components/Dashboard.vue';
import InstanceWorkspace from './components/InstanceWorkspace.vue';
import CreateInstance from './components/CreateInstance.vue';
import InviteDialog from './components/InviteDialog.vue';
import TaskCenter from './components/TaskCenter.vue';
import ApplicationSettings from './components/ApplicationSettings.vue';
import ContentLibrary from './components/ContentLibrary.vue';
import IndexRecovery from './components/IndexRecovery.vue';
import VersionManager from './components/VersionManager.vue';
import './setup.css';
const d=createDesktop();provide(desktopKey,d);
const {state,native,page,selected,active,error,connectionError,toast,modal,versionsOpen,theme}=d;
const attention=computed(()=>state.value.tasks.filter(t=>t.status==='failed'&&!d.preferences.value.dismissedTasks.includes(t.id)).length);
const ongoing=computed(()=>state.value.tasks.filter(t=>t.status==='running').length);
const navigation=[{id:'home' as const,label:'首页',icon:Home},{id:'content' as const,label:'内容库',icon:Library},{id:'tasks' as const,label:'任务中心',icon:Activity},{id:'settings' as const,label:'应用设置',icon:Settings2}];
onMounted(d.start);onUnmounted(d.stop);
</script>
<template>
 <div class="desktop-shell">
  <header class="titlebar"><button class="brand" aria-label="返回所有酒馆" @click="d.navigate('home')"><span class="mark"><Flame :size="22"/></span><b>余烬桌面</b></button><div class="titlebar-center"><span class="connection-indicator"/>{{active?.name||'本机工作区'}}<small>{{state.build?.desktop_version||state.launcher_version}}</small></div><div class="titlebar-right"><button class="version-button" aria-label="更新与版本" title="更新与版本" @click="versionsOpen=true"><Download :size="18"/><span v-if="state.desktop_updates?.available||active?.update?.available" class="update-dot"/></button><button aria-label="通知与任务" title="通知与任务" @click="d.navigate('tasks')"><Bell :size="18"/><span v-if="attention||ongoing" class="update-dot"/></button><span class="window-separator"/><button v-if="native" aria-label="最小化" @click="invoke('window',{action:'minimize'})"><Minus :size="18"/></button><button v-if="native" aria-label="最大化或还原" @click="invoke('window',{action:'maximize'})"><Maximize2 :size="15"/></button><button v-if="native" class="window-close" aria-label="关闭" @click="invoke('window',{action:'close'})"><X :size="18"/></button></div></header>
  <div v-if="!native" class="preview-note"><ShieldCheck :size="15"/>开发预览 · 隔离试玩数据 · 请勿填写真实 API 密钥</div>
  <div v-if="connectionError" class="connection-banner" role="status"><WifiOff :size="17"/><span>管理服务暂时无法连接。当前显示上次同步的状态。</span><button @click="d.refresh()">重试连接</button></div>
  <div v-if="error" class="error-banner" role="alert"><span>{{error}}</span><button @click="error=''">关闭</button></div>
  <div v-if="state.connection_error" class="error-banner" role="alert"><span>{{state.connection_error}}</span><button @click="d.navigate('settings')">检查连接档案</button></div>
  <nav class="global-navigation" aria-label="桌面导航"><button v-for="item in navigation" :key="item.id" :class="{selected:page===item.id&&!selected&&!versionsOpen}" @click="versionsOpen=false;d.navigate(item.id)"><component :is="item.icon" :size="17"/>{{item.label}}<span v-if="item.id==='tasks'&&ongoing" class="nav-count">{{ongoing}}</span></button><span class="global-navigation-note"><ShieldCheck :size="14"/>房主的本机工作台</span></nav>
  <VersionManager v-if="versionsOpen" :updates="state.desktop_updates" :instance="active" @close="versionsOpen=false" @refresh="d.refresh"/>
  <template v-else-if="page==='home'">
   <template v-if="!selected"><div v-if="state.index_recovery" class="recovery-container"><IndexRecovery :report="state.index_recovery" :root="state.root" @restored="d.recovered" @error="error=$event"/></div><div v-if="state.desktop_updates?.available" class="dashboard-update"><Download :size="17"/><span>余烬桌面 {{state.desktop_updates.latest?.version}} 已发布</span><button @click="versionsOpen=true">查看更新 <ArrowRight :size="14"/></button></div><Dashboard/></template>
   <InstanceWorkspace v-else/>
  </template>
  <TaskCenter v-else-if="page==='tasks'"/>
  <ApplicationSettings v-else-if="page==='settings'"/>
  <ContentLibrary v-else-if="page==='content'"/>
  <footer class="desktop-footer"><span><span class="connection-indicator"/>{{connectionError?'等待重新连接':'本机管理服务'}}<span v-if="ongoing"> · {{ongoing}} 个任务进行中</span></span><div class="theme-choices"><span>外观</span><button v-for="item in ([['ember','余烬'],['moonlit','月下'],['light','浅色']] as const)" :key="item[0]" :class="['theme-dot',item[0],{active:theme===item[0]}]" :aria-label="'主题 '+item[1]" :title="item[1]" @click="d.setTheme(item[0])"/></div></footer>
  <CreateInstance v-if="modal==='create'"/>
  <InviteDialog v-if="modal==='invite'"/>
  <div v-if="toast" class="toast" role="status"><Check :size="17"/>{{toast}}<button @click="toast=''" aria-label="关闭通知"><X :size="15"/></button></div>
 </div>
</template>
