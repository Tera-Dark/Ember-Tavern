(() => {
 const sdk=EmberSDK,root=document.getElementById('plugin-root');let ctx,layout,tokens=[],selected='',drag=null,lastPreview=0,ignoreClick=0,zoom=false;
 const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const colors=['#d8b675','#9fc5b0','#afa5d2','#a2bccc','#d39f8b'];
 root.innerHTML=`<style>.map-title{display:flex;justify-content:space-between;gap:15px;margin-bottom:14px;align-items:center}.map-title h2{font-size:19px;font-weight:500}.stage{height:425px;overflow:auto;border:1px solid var(--border);border-radius:8px;background:#14211d;position:relative}.stage svg{display:block;width:100%;height:100%}.stage.zoom svg{min-width:900px;min-height:600px}.token{cursor:grab;touch-action:none}.token.locked{cursor:default}.token text{pointer-events:none}.footer{justify-content:space-between;margin-top:12px}.map-empty{height:450px;display:grid;place-content:center;text-align:center;color:var(--muted);border:1px dashed var(--border);border-radius:8px}.map-empty b{font-size:20px;color:var(--gold);font-weight:500}.map-empty p{max-width:360px;font-size:12px;line-height:1.9;margin-top:16px}.position{font-size:11px;color:var(--muted)}.legend span{display:flex;align-items:center;gap:5px;font-size:10px}.legend i{height:7px;width:7px;border-radius:2px}</style><div id="view"></div>`;
 const controllable=t=>ctx.is_owner||t.assigned_to===ctx.user.id;
 function draw(c){
   const previousMap=layout?.id,previousBranch=ctx?.branch;
   ctx=c;layout=c.resources['scene.map/v1']?.data;tokens=c.resources['scene.tokens/v1']?.data.tokens||[];
   if(drag&&previousMap===layout?.id&&previousBranch===c.branch)return;
   if(drag){drag=null;ignoreClick=Date.now()+200;}
   const view=root.querySelector('#view');
   if(!layout){view.innerHTML=`<div class="map-empty"><b>让地图成为故事的一部分</b><p>${c.integrations['map-generator']?'使用上方的独立生成器创建第一张场景地图。':'到「模块中心」开启地图生成器；也可以由新的社区生成器发布 scene.map/v1 资源。'}</p><span class="note">关闭模块保留数据 · 地图与位置可随事件回档</span></div>`;return;}
   if(!tokens.some(t=>t.id===selected&&controllable(t)))selected=tokens.find(controllable)?.id||'';
   const width=layout.width*40,height=layout.height*40;
   let tiles='';
   for(let y=0;y<layout.height;y++)for(let x=0;x<layout.width;x++){
     const t=layout.grid[y][x],fill={'.':'url(#stone)','#':'#465043','~':'url(#water)','t':'#264a35','=':'#988068'}[t];
     tiles+=`<rect x="${x*40}" y="${y*40}" width="40" height="40" fill="${fill}" stroke="#12231b" stroke-opacity=".25"/>`;
     if(t==='#')tiles+=`<path d="M${x*40+4} ${y*40+6}h32v28h-32z M${x*40+4} ${y*40+17}h32" fill="none" stroke="#a4aa85" stroke-opacity=".25"/>`;
     if(t==='t')tiles+=`<circle cx="${x*40+20}" cy="${y*40+20}" r="15" fill="#315b3e" stroke="#54704a" stroke-width="2"/><circle cx="${x*40+15}" cy="${y*40+15}" r="7" fill="#3e6748"/>`;
   }
   const glyph={feather:'↗',shield:'♜',sword:'†',book:'▣',spark:'✦'};
   let figures='';tokens.forEach((t,i)=>{if(!t.position)return;const color=colors[i%colors.length];figures+=`<g data-token="${t.id}" class="token ${controllable(t)?'':'locked'}" transform="translate(${(t.position.x+.5)*40},${(t.position.y+.5)*40})"><title>${esc(t.name)} · ${t.position.x+1}, ${t.position.y+1}</title><circle r="18" fill="#10221c" stroke="${color}" stroke-width="2.5"/><circle r="14" fill="${color}" fill-opacity=".22"/><text y="5" text-anchor="middle" font-size="18" fill="${color}">${glyph[t.avatar]||'✦'}</text><text y="31" font-size="10" fill="#f3ead7" text-anchor="middle" paint-order="stroke" stroke="#18221e" stroke-width="3">${esc(t.name.split('·')[0])}</text></g>`;});
   view.innerHTML=`<div class="map-title"><div><h2>${esc(layout.title)}</h2><p class="note">${layout.width} × ${layout.height} 方格 · ${layout.source==='ai'?'AI 结构化布局':'程序生成布局'} · 种子 ${esc(layout.seed??'—')}</p></div><span class="badge">实时共享地图</span></div><div class="row" style="margin-bottom:12px"><label>操控角色<select id="actor">${tokens.filter(controllable).map(t=>`<option value="${t.id}" ${selected===t.id?'selected':''}>${esc(t.name)}</option>`).join('')||'<option>未分配可移动角色</option>'}</select></label><button id="zoom">${zoom?'适应窗口':'放大地图'}</button><span class="position" id="position">拖动角色图标，或选角色后点击可走格</span></div><div class="stage ${zoom?'zoom':''}" id="stage"><svg viewBox="0 0 ${width} ${height}" aria-label="共享场景地图"><defs><pattern id="stone" width="40" height="40" patternUnits="userSpaceOnUse"><rect width="40" height="40" fill="#747666"/><path d="M0 0h40v40H0z M0 20h40 M20 0v20" fill="none" stroke="#8b907d" stroke-width="1" opacity=".4"/></pattern><pattern id="water" width="40" height="40" patternUnits="userSpaceOnUse"><rect width="40" height="40" fill="#284c52"/><path d="M4 10q8-5 16 0t16 0 M0 28q8-5 16 0t16 0" fill="none" stroke="#69968e" opacity=".5"/></pattern></defs><g id="board">${tiles}${figures}</g></svg></div><div class="row footer"><div class="row legend"><span><i style="background:#747666"></i>地面</span><span><i style="background:#465043"></i>墙</span><span><i style="background:#284c52"></i>水域</span><span><i style="background:#315b3e"></i>树林</span></div><span class="note" style="margin:0">预览不写历史 · 松手提交才生成位置事件</span></div>`;
   root.querySelector('#actor').onchange=e=>selected=e.target.value;
   root.querySelector('#zoom').onclick=()=>{zoom=!zoom;draw(ctx);};
   const svg=root.querySelector('svg');
   function point(e){const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());return {x:Math.max(0,Math.min(layout.width-1,p.x/40-.5)),y:Math.max(0,Math.min(layout.height-1,p.y/40-.5))};}
   svg.onpointerdown=e=>{
     const node=e.target.closest('[data-token]');if(!node)return;
     const token=tokens.find(t=>t.id===node.dataset.token);if(!token||!controllable(token))return;
     selected=token.id;root.querySelector('#actor').value=selected;drag={id:selected,node,map_id:layout.id};svg.setPointerCapture(e.pointerId);e.preventDefault();
   };
   svg.onpointermove=e=>{
     if(!drag)return;const p=point(e);drag.node.setAttribute('transform',`translate(${(p.x+.5)*40},${(p.y+.5)*40})`);
     root.querySelector('#position').textContent=`${Math.round(p.x)+1}, ${Math.round(p.y)+1} · 正在拖动`;
     if(Date.now()-lastPreview>80){lastPreview=Date.now();sdk.signal('preview',{character_id:drag.id,map_id:drag.map_id,...p},ctx.resources['scene.tokens/v1']?.owner||'map-tokens');}
   };
   svg.onpointerup=async e=>{
     if(!drag)return;const p=point(e),id=drag.id,map_id=drag.map_id;drag=null;ignoreClick=Date.now()+200;
     try{await sdk.invoke('move',{character_id:id,map_id,x:Math.round(p.x),y:Math.round(p.y)},ctx.resources['scene.tokens/v1']?.owner||'map-tokens');}catch(error){sdk.notify(error.message,'error');draw(ctx);}
   };
   svg.onpointercancel=()=>{drag=null;ignoreClick=Date.now()+200;draw(ctx);};
   svg.onclick=async e=>{
     if(!selected||Date.now()<ignoreClick||e.target.closest('[data-token]'))return;
     const p=new DOMPoint(e.clientX,e.clientY).matrixTransform(svg.getScreenCTM().inverse());
     try{await sdk.invoke('move',{character_id:selected,map_id:layout.id,x:Math.floor(p.x/40),y:Math.floor(p.y/40)},ctx.resources['scene.tokens/v1']?.owner||'map-tokens');}catch(error){sdk.notify(error.message,'error');}
   };
 }
 sdk.onContext(draw);
 sdk.onSignal(message=>{
   if(!ctx||message.plugin_id!==ctx.resources['scene.tokens/v1']?.owner||message.name!=='preview'||!layout||message.payload.map_id!==layout.id||drag?.id===message.payload.character_id)return;
   const p=message.payload,node=root.querySelector(`[data-token="${p.character_id}"]`);
   if(node){node.style.transition='transform 75ms linear';node.setAttribute('transform',`translate(${(p.x+.5)*40},${(p.y+.5)*40})`);node.dataset.previewTime=String(Date.now());}
 });
 setInterval(()=>{if(root.querySelector('[data-preview-time]')&&!drag){const nodes=[...root.querySelectorAll('[data-preview-time]')];if(nodes.some(n=>Date.now()-Number(n.dataset.previewTime)>1500))draw(ctx);}},700);
})();
