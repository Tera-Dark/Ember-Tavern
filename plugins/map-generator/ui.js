(() => {
 const sdk=EmberSDK,root=document.getElementById('plugin-root');let ctx,busy=false;
 root.innerHTML=`<div class="card"><div class="row"><span class="badge">独立地图生成器</span><label>地形<select id="theme"><option value="harbor">雾港码头</option><option value="ruins">古老遗迹</option><option value="forest">边境森林</option><option value="cave">回声洞穴</option></select></label><label>来源<select id="mode"><option value="procedural">程序生成（无 API）</option><option value="ai">AI 布局（需配置）</option></select></label><label>种子<input id="seed" style="width:100px" inputmode="numeric" placeholder="随机" /></label><button class="primary" id="generate">生成地图</button></div><p class="note" id="tip">可重复种子生成网格；AI 模式使用决策接口，不冒充图像模型生成的美术地图。新布局会重新定位角色。</p></div>`;
 sdk.onContext(c=>{ctx=c;root.querySelector('#generate').disabled=!c.is_owner||busy;root.querySelector('#mode option[value=ai]').disabled=!c.resources['map.generator/v1']?.data.ai_configured;});
 root.querySelector('#generate').onclick=async()=>{
   busy=true;const b=root.querySelector('#generate');b.disabled=true;b.textContent='正在生成…';
   try {await sdk.invoke('generate',{theme:root.querySelector('#theme').value,mode:root.querySelector('#mode').value,seed:root.querySelector('#seed').value||null,width:24,height:16});sdk.notify('地图已生成，角色位置已同步');}
   catch(e){sdk.notify(e.message,'error');}finally{busy=false;b.disabled=!ctx?.is_owner;b.textContent='生成地图';}
 };
})();
