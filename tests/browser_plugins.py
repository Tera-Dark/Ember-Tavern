"""Module/iframe/two-player drag + rewind acceptance; no provider key needed.
python tests/browser_plugins.py --base-url http://127.0.0.1:8000 --screenshots artifacts/plugins
Uses a stub ONLY for browser speechSynthesis; not an audible/real TTS test.
"""
import argparse,asyncio,json,secrets,time
from pathlib import Path
from playwright.async_api import async_playwright,expect

async def run(base_url,screenshots):
 suffix=secrets.token_hex(4);password='Qa_'+secrets.token_urlsafe(18);errors=[];console=[];report={};out=Path(screenshots) if screenshots else None
 if out:out.mkdir(parents=True,exist_ok=True)
 async with async_playwright() as p:
  browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
  a=await browser.new_context(viewport={'width':1440,'height':1080});b=await browser.new_context(viewport={'width':1440,'height':1080})
  await a.add_init_script('window.__speechText=""; window.speechSynthesis.speak = u => { window.__speechText=u.text; };')
  host=await a.new_page();player=await b.new_page()
  for page in (host,player):
   page.on('pageerror',lambda e:errors.append(str(e)))
   page.on('console',lambda m:console.append(m.text) if m.type=='error' else None)
  async def signup(page,username,name):
   await page.goto(base_url,wait_until='networkidle');await page.get_by_role('button',name='加入酒馆',exact=False).click();dialog=page.get_by_role('dialog')
   await dialog.get_by_label('用户名',exact=True).fill(username);await dialog.get_by_label('桌边的称呼',exact=True).fill(name);await dialog.get_by_label('密码',exact=True).fill(password)
   await dialog.get_by_role('button',name='注册并进入大厅',exact=True).click();await page.get_by_role('heading',name='晚上好，'+name,exact=False).wait_for()
  async def token(page):return await page.evaluate("() => sessionStorage.getItem('ember-session')")
  async def state(page,rid):
   response=await page.request.get(base_url+'/api/rooms/'+rid,headers={'Authorization':'Bearer '+await token(page)})
   assert response.ok,await response.text();return await response.json()
  await signup(host,'mod_host_'+suffix,'模块验收房主');await host.get_by_role('button',name='创建冒险',exact=True).click()
  await host.get_by_role('dialog').get_by_label('冒险名称',exact=True).fill('模块化双人验证 · '+suffix)
  await host.get_by_role('button',name='创建并进入房间',exact=True).click();await host.get_by_role('heading',name='冒险现场',exact=True).wait_for()
  rid=host.url.rsplit('/',1)[1];initial=await state(host,rid)
  await signup(player,'mod_friend_'+suffix,'地图同伴');await player.get_by_role('button',name='加入房间',exact=True).click()
  await player.get_by_role('dialog').get_by_label('房间邀请码',exact=True).fill(initial['code']);await player.get_by_role('dialog').get_by_role('button',name='加入冒险',exact=True).click();await player.get_by_role('heading',name='冒险现场',exact=True).wait_for()
  own=await player.request.get(base_url+'/api/auth/me',headers={'Authorization':'Bearer '+await token(player)});friend=(await own.json())['id'];char=initial['state']['characters'][1]['id']
  await host.get_by_role('button',name='角色档案',exact=False).first.click();await host.get_by_label('分配角色 洛恩·灯誓').select_option(friend)
  await host.get_by_role('button',name='模块中心',exact=True).click()
  for name in ['地图生成器','角色图标与移动','TTS 旁白']:
   switch=host.get_by_role('switch',name='开关 '+name,exact=True);await switch.click();await expect(switch).to_have_attribute('aria-checked','true')
  if out:await host.screenshot(path=str(out/'module-center.png'),full_page=True)
  await player.get_by_role('button',name='模块中心',exact=True).click();await expect(player.get_by_role('switch',name='开关 地图生成器')).to_be_disabled()
  await host.get_by_role('button',name='场景地图',exact=False).first.click();await player.get_by_role('button',name='场景地图',exact=False).first.click()
  gen=host.frame_locator('iframe[title="插件 · 地图生成器"]');hm=host.frame_locator('iframe[title="插件 · 场景地图"]');pm=player.frame_locator('iframe[title="插件 · 场景地图"]')
  await gen.get_by_label('种子',exact=True).fill('42');await gen.get_by_role('button',name='生成地图',exact=True).click()
  await hm.get_by_role('heading',name='雾港 · 旧码头',exact=True).wait_for();await pm.get_by_role('heading',name='雾港 · 旧码头',exact=True).wait_for()
  baseline=await state(host,rid);target=baseline['events'][-1];layout=baseline['state']['_plugins']['scene-map']['data']['map'];position=baseline['state']['_plugins']['map-tokens']['data']['positions'][char]
  await expect(pm.locator('#actor')).to_have_value(char)
  before=f"translate({(position['x']+.5)*40:g},{(position['y']+.5)*40:g})";marker='[data-token="'+char+'"]'
  await pm.locator(marker).scroll_into_view_if_needed();await hm.locator(marker).scroll_into_view_if_needed()
  box=await pm.locator(marker).bounding_box();frame_box=await player.locator('iframe[title="插件 · 场景地图"]').bounding_box()
  matrix=await pm.locator('svg').evaluate('(el) => {let m=el.getScreenCTM();return {a:m.a,d:m.d,e:m.e,f:m.f};}')
  dest_x=frame_box['x']+matrix['e']+6.5*40*matrix['a'];dest_y=frame_box['y']+matrix['f']+8.5*40*matrix['d']
  await player.mouse.move(box['x']+box['width']/2,box['y']+12);await player.mouse.down();start=time.monotonic();await player.mouse.move(dest_x,dest_y,steps=8)
  await expect(hm.locator(marker)).not_to_have_attribute('transform',before)
  report['drag_preview_sync_ms']=round((time.monotonic()-start)*1000)
  during=await state(host,rid);assert during['state']['_plugins']['map-tokens']['data']['positions'][char]==position
  assert during['revision']==baseline['revision'];report['preview_not_persisted']=True
  await player.mouse.up();await expect(hm.locator(marker)).to_have_attribute('transform','translate(260,340)')
  # The preview can reach the final coordinate first, so wait for the persisted UI event too.
  await host.get_by_role('button',name='事件档案',exact=False).first.click();await expect(host.locator('.record-list')).to_contain_text('洛恩·灯誓 移动到 (7, 9)')
  committed=await state(host,rid);assert committed['state']['_plugins']['map-tokens']['data']['positions'][char]=={'x':6,'y':8};report['move_committed']=True
  await host.get_by_role('button',name='台本与声音',exact=False).first.click();script=host.frame_locator('iframe[title="插件 · 旁白台本"]');tts=host.frame_locator('iframe[title="插件 · TTS 旁白"]')
  await script.locator('textarea').first.fill('撤销的未来旁白 '+suffix);await script.get_by_role('button',name='保存片段',exact=True).first.click()
  await expect(tts.locator('#line option').first).to_contain_text('撤销的未来旁白')
  await expect(tts.get_by_role('button',name='生成并保存真实音频',exact=True)).to_be_disabled()
  await tts.get_by_role('button',name='浏览器朗读',exact=True).click();await expect(host.locator('.toast')).to_contain_text('已交给浏览器语音引擎');assert (await host.evaluate('() => window.__speechText')).startswith('撤销的未来旁白');report['speech_bridge_stub']=True
  if out:await host.screenshot(path=str(out/'script-and-voice.png'),full_page=True)
  iframe=host.locator('iframe[title="插件 · TTS 旁白"]');assert await iframe.get_attribute('sandbox')=='allow-scripts'
  child=next(f for f in host.frames if '/plugin-frame/voice-tts' in f.url)
  assert await child.evaluate("() => {try {return parent.document.title;} catch(e){return 'blocked';}}")=='blocked'
  ctx=await child.evaluate('() => EmberSDK.getContext()');assert await token(host) not in json.dumps(ctx);report['iframe_isolation']=True
  await host.get_by_role('button',name='事件档案',exact=False).first.click();record=host.locator('.record-list article').filter(has=host.get_by_text('#'+str(target['seq']),exact=True))
  await record.get_by_role('button',name='回档',exact=True).click();await host.get_by_role('dialog').get_by_role('button',name='确认回档',exact=True).click();await host.get_by_role('dialog').wait_for(state='hidden')
  await expect(pm.locator(marker)).to_have_attribute('transform',before);restored=await state(host,rid)
  assert restored['branch']==2 and restored['state']['_plugins']['map-tokens']['data']['positions']==baseline['state']['_plugins']['map-tokens']['data']['positions']
  assert restored['state']['_plugins']['narrator-script']['data']==baseline['state']['_plugins']['narrator-script']['data'];report['map_script_rollback']=True
  await host.get_by_role('button',name='场景地图',exact=False).first.click()
  if out:await host.screenshot(path=str(out/'shared-map.png'),full_page=True)
  await host.get_by_role('button',name='模块中心',exact=True).click();switch=host.get_by_role('switch',name='开关 场景地图',exact=True);await switch.click()
  await host.get_by_role('dialog').get_by_role('button',name='确认关闭',exact=True).click();await expect(switch).to_have_attribute('aria-checked','false')
  disabled=await state(host,rid);assert disabled['state']['_plugins']['scene-map']['data']==baseline['state']['_plugins']['scene-map']['data'];report['disable_retains_data']=True
  await switch.click();await expect(switch).to_have_attribute('aria-checked','true')
  # Optional installed community template: automatic catalog + dynamic navigation.
  if any(p['id']=='session-insights' for p in disabled['plugins']):
   other=host.get_by_role('switch',name='开关 会话观察板',exact=True);await other.click();await expect(other).to_have_attribute('aria-checked','true')
   await host.get_by_role('button',name='会话观察板',exact=False).first.click();await host.frame_locator('iframe[title="插件 · 会话观察板"]').get_by_role('heading',name='模块化双人验证 · '+suffix+' · 观察板',exact=True).wait_for();report['hot_installed_ui_plugin']=True
   if out:await host.screenshot(path=str(out/'community-plugin.png'),full_page=True)
  # Phone layout; module pages and nested iframe have no horizontal overflow.
  await host.set_viewport_size({'width':390,'height':844});await host.get_by_role('button',name='场景地图',exact=False).first.click()
  await hm.get_by_role('heading',name='雾港 · 旧码头',exact=True).wait_for()
  assert not await host.evaluate('() => document.documentElement.scrollWidth > innerWidth')
  mapchild=next(f for f in host.frames if '/plugin-frame/scene-map' in f.url);assert not await mapchild.evaluate('() => document.documentElement.scrollWidth > innerWidth');report['mobile_no_horizontal_overflow']=True
  if out:await host.screenshot(path=str(out/'mobile-map.png'),full_page=True)
  await host.get_by_role('button',name='台本与声音',exact=False).first.click();await tts.get_by_role('button',name='浏览器朗读',exact=True).wait_for()
  voicechild=next(f for f in host.frames if '/plugin-frame/voice-tts' in f.url)
  assert not await voicechild.evaluate('() => document.documentElement.scrollWidth > innerWidth');report['mobile_voice_no_horizontal_overflow']=True
  if out:await host.screenshot(path=str(out/'mobile-voice.png'),full_page=True)
  assert not errors,errors;assert not console,console;report.update({'page_errors':errors,'console_errors':console,'room_id':rid,'room_code':initial['code']})
  print(json.dumps(report,ensure_ascii=False,indent=2));await browser.close()

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--base-url',default='http://127.0.0.1:8000');parser.add_argument('--screenshots');args=parser.parse_args();asyncio.run(run(args.base_url,args.screenshots))
