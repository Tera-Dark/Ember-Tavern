(() => {
  const root=document.getElementById('plugin-root');
  const text=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  EmberSDK.onContext(context=>{
    const campaign=context.resources['core.campaign/v1']?.data?.campaign;
    if(!campaign){root.innerHTML='<div class="card"><h2>剧本罗盘</h2><p class="note">这间房间使用自由世界，没有结构化剧本。旧冒险仍可正常游玩。</p></div>';return;}
    root.innerHTML=`<div class="card"><span class="badge">只读 HUD · 无宿主 DOM／令牌／写状态能力</span><h2>${text(campaign.scene_title)}</h2><p>${text(campaign.objective)}</p><span class="badge">${campaign.completed?'已收束':'进行中'} · v${text(campaign.version)}</span><h3>已揭示线索</h3>${campaign.revealed_clues.map(clue=>`<article style="padding:12px 0;border-top:1px solid var(--border)"><b>${text(clue.title)}</b><p class="note">${text(clue.text)}</p></article>`).join('')||'<p class="note">还没有公开揭示的线索。</p>'}<p class="note">core.campaign/v1 只提供服务端公开投影，不包含 GM 指引、未来节点或未揭示线索。即使房主打开此只读资源也不下发秘密。</p></div>`;
  });
})();
