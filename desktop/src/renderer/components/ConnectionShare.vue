<script setup lang="ts">
import {computed,ref,watch} from 'vue';
import {Copy,QrCode,Wifi} from 'lucide-vue-next';
import {guestEntryQR,guestEntryURL} from '../guestEntry';
import {useDesktop} from '../useDesktop';
import type {Instance} from '../../types';
const props=defineProps<{instance:Instance}>();const emit=defineEmits<{selected:[url:string];message:[value:string]}>();const d=useDesktop();
const chosen=ref(''),visible=ref(false);
const entries=computed(()=>props.instance.lan_urls.flatMap(base=>{try{return [{base,url:guestEntryURL(base)}];}catch{return [];}}));
watch(()=>props.instance.id+':'+entries.value.map(e=>e.base).join('|'),()=>{if(!entries.value.some(e=>e.base===chosen.value)){const remembered=entries.value.find(e=>e.url===d.shareAddresses.value[props.instance.id]);chosen.value=remembered?.base||(entries.value.length===1?entries.value[0].base:'');}},{immediate:true});
watch([chosen,()=>props.instance.id],()=>{const entry=entries.value.find(e=>e.base===chosen.value),url=entry?.url||'';if(url)d.shareAddresses.value[props.instance.id]=url;else delete d.shareAddresses.value[props.instance.id];emit('selected',url);},{immediate:true});
const code=computed(()=>chosen.value?guestEntryQR(chosen.value):undefined);
</script>
<template><section class="connection-share"><template v-if="entries.length"><div class="connection-select"><label><Wifi :size="17"/>同伴的浏览器入口<select v-model="chosen" aria-label="选择同伴入座地址"><option value="" disabled>先选择同伴可访问的网卡地址</option><option v-for="entry in entries" :key="entry.base" :value="entry.base">{{entry.base}}</option></select></label><button class="secondary" :disabled="!chosen" @click="d.copy(guestEntryURL(chosen))"><Copy :size="15"/>复制入口</button><button class="secondary" :disabled="!chosen" :aria-expanded="visible" @click="visible=!visible"><QrCode :size="17"/>{{visible?'收起二维码':'显示二维码'}}</button></div><p v-if="entries.length>1" class="help-text">检测到多个网卡地址。请选择同伴所在的 LAN 或 VPN；地址存在不代表对方已连通。</p><div v-if="visible&&code" class="entry-qr"><img :src="code.image" alt="同伴浏览器入口二维码"/><div><b>扫码打开同伴入座页</b><code>{{code.url}}</code><p>二维码只包含服务入口。身份和一次性密钥请私下单独提供。</p></div></div></template><p v-else class="warning">{{instance.lan?'没有发现可分享的 LAN 地址，请检查网卡或运行本机自检。':'当前只允许本机访问，停止实例后可开启 LAN。'}} 请勿把 localhost 发给同伴。</p></section></template>
