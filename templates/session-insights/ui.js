(() => {
 const root=document.getElementById('plugin-root');
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 EmberSDK.onContext(ctx=>{
  const r=ctx.room;
  root.innerHTML=`<div class="card"><span class="badge">真正独立安装的社区 UI 示例</span><h2 style="font-size:23px;margin:20px 0 13px">${esc(r.title)} · 观察板</h2><p class="note">此插件从安装目录加载。宿主源码和前端打包配置没有注册它的名字。</p><div class="row" style="margin:25px 0"><span class="badge">第 ${r.turn} 轮</span><span class="badge">${r.characters.length} 个角色</span><span class="badge">最近 ${ctx.events.length} 条有效事件</span><span class="badge">时间线 ${ctx.branch}</span></div>${r.characters.map(c=>`<div class="row" style="padding:15px 0;border-top:1px solid var(--border);justify-content:space-between"><b>${esc(c.name)}</b><span class="muted">生命 ${c.hp}/${c.max_hp} · 压力 ${c.stress}/6</span></div>`).join('')}<p class="note" style="margin-top:24px">权限仅为 read:room、read:events；没有网络、宿主 DOM、令牌或写状态能力。</p></div>`;
 });
})();
