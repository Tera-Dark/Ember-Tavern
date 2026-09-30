(() => {
 const sdk=EmberSDK,root=document.getElementById('plugin-root');let ctx,chosen='',busy=false,audio=new Audio(),last='';
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function render(c){ctx=c;const lines=c.resources['narration.script/v1']?.data.lines||[],status=c.resources['narration.audio/v1']?.data||{};
   const fingerprint=JSON.stringify([c.plugin_revision,lines.map(l=>[l.id,l.speaker,l.text]),c.voices,status.configured]);if(last===fingerprint)return;last=fingerprint;
   if(!lines.some(l=>l.id===chosen))chosen=lines[0]?.id||'';
   root.innerHTML=`<div class="card"><div class="row" style="justify-content:space-between"><span class="badge">独立 TTS 输出模块</span><small>${status.configured?'外部 TTS 已配置（待调用验证）':'外部 TTS 未配置 · 可试浏览器朗读'}</small></div><div class="row" style="margin-top:15px"><label>片段<select id="line" style="max-width:300px">${lines.map((l,i)=>`<option value="${l.id}" ${l.id===chosen?'selected':''}>${i+1}. ${esc(l.speaker)} · ${esc(l.text.slice(0,28))}</option>`).join('')||'<option>暂无台本</option>'}</select></label><label>本地声线<select id="voice" style="max-width:160px"><option value="">系统默认</option>${(c.voices||[]).filter(v=>v.lang.startsWith('zh')).map(v=>`<option value="${esc(v.name)}">${esc(v.name)}</option>`).join('')}</select></label><button id="speak" ${lines.length?'':'disabled'}>浏览器朗读</button><button id="stop">停止</button></div><div class="row" style="margin-top:12px"><button class="primary" id="generate" ${status.configured&&c.is_owner&&!c.user.guest&&lines.length&&!busy?'':'disabled'}>生成并保存真实音频</button><small>本地朗读不会生成文件；外部 TTS 由服务商实际合成 MP3。</small></div><div class="row" id="clips" style="margin-top:13px">${(c.own_state.clips||[]).slice(-3).reverse().map((clip,i)=>`<span class="row"><span class="badge">${esc(clip.speaker)} · ${(clip.bytes/1024).toFixed(1)} KiB</span><button data-play="${clip.id}">播放音频</button><button data-download="${clip.id}">下载 MP3</button></span>`).join('')}</div></div>`;
   root.querySelector('#line').onchange=e=>chosen=e.target.value;
   root.querySelector('#speak').onclick=async()=>{const line=lines.find(l=>l.id===chosen);if(!line)return;try{await sdk.speak(line.text,{voice:root.querySelector('#voice').value,lang:'zh-CN',rate:1});sdk.notify('已交给浏览器语音引擎；声线可用性取决于你的设备');}catch(e){sdk.notify(e.message,'error');}};
   root.querySelector('#stop').onclick=()=>{audio.pause();sdk.stopSpeech().catch(()=>{});};
   root.querySelector('#generate').onclick=async()=>{busy=true;const btn=root.querySelector('#generate');btn.disabled=true;btn.textContent='正在合成…';try{await sdk.invoke('synthesize',{line_id:chosen});sdk.notify('真实音频已保存，可播放或下载');}catch(e){sdk.notify(e.message,'error');}finally{busy=false;last='';render(ctx);}};
   root.querySelectorAll('[data-play]').forEach(b=>b.onclick=async()=>{try{const result=await sdk.audio(b.dataset.play);audio.pause();audio.src=result.data_uri;await audio.play();}catch(e){sdk.notify('无法播放：'+e.message+'。也可以下载后播放。','error');}});
   root.querySelectorAll('[data-download]').forEach(b=>b.onclick=()=>sdk.downloadAudio(b.dataset.download).catch(e=>sdk.notify(e.message,'error')));
 }
 sdk.onContext(render);
})();
