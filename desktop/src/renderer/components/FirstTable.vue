<script setup lang="ts">
import {computed,onUnmounted,ref,watch} from 'vue';
import {BookOpen,Check,Copy,KeyRound,Play,RefreshCw,Users,ShieldCheck} from 'lucide-vue-next';
import {invoke} from '../bridge';
import PresetChooser from './PresetChooser.vue';
import type {Instance,Room,Starter,Invite} from '../../types';
const props=defineProps<{instance:Instance;native:boolean}>();
const emit=defineEmits<{open:[roomId:string];error:[message:string];message:[message:string]}>();
const starters=ref<Starter[]>([]);const rooms=ref<Room[]>([]);const current=ref<Room|null>(null);const invites=ref<Invite[]>([]);
const selectedStarter=ref<'harbor'|'frontier'>('harbor');const title=ref('我们的第一夜');const identity=ref('');const issued=ref<Invite|null>(null);
const busy=ref(false);const fetching=ref(false);const error=ref('');let disposed=false;let generation=0;
const selected=computed(()=>starters.value.find(item=>item.id===selectedStarter.value));
const currentStarter=computed(()=>starters.value.find(item=>item.world_title===current.value?.state?.world?.title));
const members=computed(()=>Array.isArray(current.value?.members)?current.value!.members:[]);
const characters=computed(()=>current.value?.state?.characters||[]);
const ready=computed(()=>props.instance.status==='running');
const links=computed(()=>props.instance.lan_urls.map(url=>url+'/?guest=1'));
const storageKey=computed(()=>'ember-first-table-room-'+props.instance.id);
const stage=computed(()=>!ready.value?0:!current.value?1:!invites.value.some(item=>item.user_id&&item.enabled)?2:3);

function remember(roomId:string){try{localStorage.setItem(storageKey.value,roomId);}catch{/* local storage is optional */}}
async function reloadRoom(roomId:string){
  const epoch=generation;const instanceId=props.instance.id;
  const [room,guestList]=await Promise.all([invoke<Room>('room',{instanceId,roomId}),invoke<Invite[]>('guestInvites',{instanceId,roomId})]);
  if(!disposed&&generation===epoch){current.value=room;invites.value=guestList;}
}
async function load(){
  if(!ready.value||fetching.value||busy.value||disposed)return;
  fetching.value=true;const epoch=generation;
  try{
    const [worlds,list]=await Promise.all([invoke<Starter[]>('starterWorlds',{instanceId:props.instance.id}),invoke<Room[]>('rooms',{instanceId:props.instance.id})]);
    if(disposed||epoch!==generation)return;
    starters.value=worlds;rooms.value=list.filter(item=>item.is_owner);
    let saved='';try{saved=localStorage.getItem(storageKey.value)||'';}catch{}
    const target=current.value?.id||saved;
    if(target&&rooms.value.some(item=>item.id===target))await reloadRoom(target);
    else if(current.value){current.value=null;invites.value=[];issued.value=null;}
  }catch(value:any){if(!disposed&&epoch===generation)error.value=value.message;}
  finally{if(epoch===generation)fetching.value=false;}
}
async function work(fn:()=>Promise<void>){
  busy.value=true;error.value='';
  try{await fn();}catch(value:any){error.value=value.message;emit('error',value.message);}
  finally{busy.value=false;}
}
async function createRoom(){await work(async()=>{
  const room=await invoke<Room>('createRoom',{instanceId:props.instance.id,title:title.value,preset:selectedStarter.value});
  remember(room.id);issued.value=null;await reloadRoom(room.id);
  rooms.value=[room,...rooms.value.filter(item=>item.id!==room.id)];
  emit('message','房间已保存；现在可以邀请同伴或单人试用。');
});}
async function fromPreset(room:Room){issued.value=null;remember(room.id);await reloadRoom(room.id);rooms.value=[room,...rooms.value.filter(item=>item.id!==room.id)];}
async function continueRoom(roomId:string){await work(async()=>{issued.value=null;await reloadRoom(roomId);remember(roomId);});}
async function issue(){if(!current.value)return;await work(async()=>{
  const reply=await invoke<{invite:Invite;room:Room}>('issueGuest',{instanceId:props.instance.id,roomId:current.value!.id,identity:identity.value.trim()});
  issued.value=reply.invite;identity.value='';await reloadRoom(current.value!.id);
});}
async function assign(characterId:string,event:Event){if(!current.value)return;const userId=(event.target as HTMLSelectElement).value||null;await work(async()=>{
  current.value=await invoke<Room>('assignCharacter',{instanceId:props.instance.id,roomId:current.value!.id,characterId,userId});
});}
async function copy(text:string){try{if(props.native)await invoke('clipboard',{text});else await navigator.clipboard.writeText(text);emit('message','已复制；请只私下发送给对应同伴。');}catch{emit('message','自动复制不可用，请选中后手动复制。');}}
watch(()=>[props.instance.id,props.instance.status],()=>{generation++;fetching.value=false;if(!ready.value){issued.value=null;return;}load();},{immediate:true});
const timer=setInterval(()=>{if(current.value&&ready.value)load();},5000);
onUnmounted(()=>{disposed=true;generation++;clearInterval(timer);issued.value=null;});
</script>
<template>
  <div class="first-table">
    <section class="welcome-panel"><div class="welcome-icon"><BookOpen :size="32"/></div><div><span class="eyebrow">FROM A WORLD TO YOUR FIRST TABLE</span><h2>开好第一桌，也能继续上一场。</h2><p>默认演示主持，无需填写 API Key。先验证多人流程，真实模型和额外能力以后按需开启。</p></div></section>
    <ol class="setup-steps" aria-label="开桌步骤"><li v-for="(name,index) in ['准备实例','选择世界','邀请同伴','分配角色与入桌']" :key="name" :class="{done:stage>index,current:stage===index}"><Check v-if="stage>index" :size="16"/><span v-else>{{index+1}}</span>{{name}}</li></ol>
    <p v-if="error" class="warning" role="alert">{{error}}</p>
    <section v-if="!ready" class="panel"><h3>先准备实例</h3><p class="help-text">请使用右上角的安装／启动按钮。已有房间和身份会保留；不要为了排错删库。安装的下载时间单独显示。</p></section>
    <template v-else>
      <PresetChooser :instance="instance" :native="native" @created="fromPreset" @error="error=$event" @message="emit('message',$event)"/>
      <section class="panel"><div class="panel-title"><h3><BookOpen :size="18"/>选择世界或继续存档</h3><button class="secondary" :disabled="busy||fetching" @click="load"><RefreshCw :size="15"/>刷新房间</button></div>
        <div v-if="rooms.length" class="existing-adventures"><p class="help-text">已有冒险无需重新创建。选中后继续原房间、角色、事件与邀请。</p><button v-for="room in rooms" :key="room.id" :class="['secondary',{selected:current?.id===room.id}]" :disabled="busy" @click="continueRoom(room.id)">{{room.title}} · 第 {{room.turn||0}} 轮</button></div>
        <div class="starter-grid"><label v-for="world in starters" :key="world.id" :class="['starter-card',{selected:selectedStarter===world.id}]"><input v-model="selectedStarter" type="radio" name="starter-world" :value="world.id" :disabled="busy"/><span class="eyebrow">{{world.category}}</span><b>{{world.name}}</b><p>{{world.description}}</p><small>{{world.suggested_players}} · ember-light/v1</small><small>{{world.label}}</small></label></div>
        <form class="inline-form" @submit.prevent="createRoom"><input v-model="title" aria-label="向导房间名称" maxlength="60" required placeholder="为新的冒险起个名字"/><button class="primary" :disabled="busy||!starters.length"><BookOpen :size="16"/>{{busy?'处理中…':'以演示创建新房间'}}</button></form>
        <p class="help-text">这是两个现有入门世界，不是完整 D&D／SLG 或社区玩法包。创建新的房间不会覆盖已有冒险；演示是规则脚本，不代表真实 AI 叙事质量。</p>
      </section>
      <section v-if="current" class="panel"><div class="panel-title"><div><span class="eyebrow">YOUR SAVED ADVENTURE</span><h2>{{current.title}}</h2><p class="help-text">{{current.state?.world?.title}} · 第 {{current.state?.turn||0}} 轮 · 已保存到此实例</p></div><span class="badge">{{current.ai_mode==='demo'?'演示 · 无模型费用':'已有房间的真实模型模式 · 可能收费'}}</span></div>
        <h3><KeyRound :size="18"/>同伴只需要浏览器</h3><p class="help-text">入口地址、身份、验证密钥分开传递；密钥不放 URL。你也可以不邀请同伴，直接单人试用。</p>
        <div v-if="links.length" class="address-list"><div v-for="url in links" :key="url"><code>{{url}}</code><button @click="copy(url)"><Copy :size="15"/>复制入口</button></div></div>
        <p v-else class="warning">{{instance.lan?'没有发现 LAN 地址，请运行本机自检。':'当前仅本机，邀请同伴前需停止实例并开启 LAN。'}} 不要给朋友 localhost 或 0.0.0.0。</p>
        <form class="inline-form" @submit.prevent="issue"><input v-model="identity" aria-label="向导同伴身份" maxlength="24" required placeholder="每位同伴一个身份，例如小林"/><button class="secondary" :disabled="busy"><KeyRound :size="16"/>生成这位同伴的密钥</button></form>
        <div v-if="issued?.verification_key" class="one-time-key"><div class="panel-title"><b>{{issued.identity}} · 密钥仅此一次显示</b><button class="text-button" @click="issued=null">隐藏密钥</button></div><input :value="issued.verification_key" aria-label="向导一次性显示的密钥" readonly @focus="($event.target as HTMLInputElement).select()"/><button class="secondary" :disabled="!links.length" @click="copy('浏览器地址：'+links[0]+'\n身份：'+issued.identity+'\n验证密钥：'+issued.verification_key)"><Copy :size="15"/>私下复制入座信息</button><p class="help-text">关闭向导后不再回显。丢失可重新生成，旧密钥立即失效；密钥不会存入浏览器本地存储。</p></div>
        <div class="guest-row" v-for="invite in invites" :key="invite.id"><Users :size="17"/><div><b>{{invite.identity}}</b><small>{{!invite.enabled?'已撤销':invite.user_id?'已验证入座':'等待同伴输入身份和密钥'}}</small></div></div>
        <hr/><h3>分配角色</h3><p class="help-text">同伴验证入座后会出现在列表。每人操控一位角色；改分配不会重置角色状态。稍后也可在冒险桌的角色档案修改。</p>
        <div v-for="character in characters" :key="character.id" class="character-assignment"><div><b>{{character.name}}</b><small>{{character.archetype}}</small></div><select :value="character.assigned_to||''" :aria-label="'分配角色 '+character.name" :disabled="busy" @change="assign(character.id,$event)"><option value="">未分配</option><option v-for="member in members" :key="member.id" :value="member.id">{{member.display_name}}{{member.role==='host'?'（房主）':''}}</option></select></div>
        <div class="notice small"><ShieldCheck :size="18"/><p>关闭桌面会停止服务，数据不会删除。下次启动同一实例，在这里选已有冒险继续；朋友继续使用原身份与密钥。</p></div>
        <p v-if="current.ai_mode==='demo'&&currentStarter" class="help-text">第一步参考：{{currentStarter.first_action}} 不确定的行动由服务器检定，模型不能掷骰或替玩家作决定。</p>
        <button class="primary" :disabled="busy||!native" @click="emit('open',current.id)"><Play :size="16"/>{{current.state?.turn?'继续这场冒险':'进入第一场冒险'}}</button><p v-if="!native" class="help-text">开发预览验证管理流程；原生冒险窗口请在 Windows EXE 中打开。同伴浏览器入口可单独验证。</p>
      </section>
    </template>
  </div>
</template>
