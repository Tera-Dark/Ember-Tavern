<script setup lang="ts">
import {X,Copy,KeyRound} from 'lucide-vue-next';
import {useDesktop} from '../useDesktop';
import {useModalFocus} from '../modalFocus';
const {modal,issued,active,copy,shareAddresses}=useDesktop();
useModalFocus('.dialog',()=>{modal.value=null;issued.value=null;});
</script>
<template>
  <div v-if="modal==='invite'" class="overlay" @click.self="modal=null;issued=null"><section class="dialog" role="dialog" aria-modal="true" :aria-label="'同伴专属密钥'"><button class="dialog-close" aria-label="关闭弹窗" @click="modal=null;issued=null"><X :size="18"/></button><span class="eyebrow">{{'INVITE ONE TRUSTED FRIEND'}}</span><template v-if="issued"><h2>{{issued.identity}}，你的座位已准备好。</h2><p>请把地址、身份与密钥私下发送给这一位同伴。</p><label class="secret-label">身份<input :value="issued.identity" readonly/></label><label class="secret-label">验证密钥 · 仅此一次显示<input :value="issued.verification_key" readonly @focus="($event.target as HTMLInputElement).select()"/></label><button class="primary full" @click="copy('身份：'+issued.identity+'\n验证密钥：'+issued.verification_key+'\n浏览器地址：'+(active?shareAddresses[active.id]||'请联系房主取得 LAN 地址':'请联系房主取得 LAN 地址'))"><Copy :size="16"/>复制入座信息</button><div class="notice small"><KeyRound :size="16"/><p>密钥不在后续列表回显。丢失请重新生成；重生成立即作废旧密钥。不要把密钥放公开链接或截图。</p></div></template></section></div>

</template>
