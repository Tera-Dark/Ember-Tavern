(() => {
 const root=document.getElementById('plugin-root');
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 EmberSDK.onContext(ctx=>{
  root.innerHTML=`<div class="card"><span class="badge">Python Backend SDK 示例</span><h2 style="margin:18px 0">场景便签</h2><p class="note">只有房主可写；便签随事件快照回档，不改正史。</p>${(ctx.own_state.notes||[]).map(text=>`<p style="border-bottom:1px solid var(--border);padding:12px 0;white-space:pre-wrap">${esc(text)}</p>`).join('')}<textarea aria-label="便签内容" maxlength="500" style="width:100%;margin-top:18px" ${ctx.is_owner?'':'disabled'}></textarea><button id="append" class="primary" style="margin-top:12px" ${ctx.is_owner?'':'disabled'}>追加便签</button></div>`;
  root.querySelector('#append').onclick=async()=>{try{await EmberSDK.invoke('append',{text:root.querySelector('textarea').value});EmberSDK.notify('便签已保存');}catch(e){EmberSDK.notify(e.message,'error');}};
 });
})();
