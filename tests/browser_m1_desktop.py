"""Real development controller/Go/host + desktop preset chooser + browser guests.
Uses only synthetic credentials from the explicitly isolated BASE64 QA preview,
not production DPAPI and never a user directory. Native Windows is tested in CI.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright,expect

ROOT=Path(__file__).resolve().parent.parent
OUTPUT=ROOT/'artifacts/desktop-m1-evidence'


async def main():
    OUTPUT.mkdir(parents=True,exist_ok=True);errors=[];report={'native_window':False,'windows_encryption_tested':False,'paid_calls':False,'human_playtest':False}
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=os.getenv('EMBER_CHROMIUM_PATH'),headless=True,args=['--no-sandbox'])
        desktop=await browser.new_page(viewport={'width':1440,'height':1080});desktop.on('pageerror',lambda error:errors.append(str(error)))
        try:
            await desktop.goto('http://127.0.0.1:8765')
            state=await desktop.evaluate("() => window.emberDesktop.invoke('state')")
            active=next((item for item in state['instances'] if item['commit'] and not item.get('recovered_from_id')),None)
            if active:
                await desktop.locator('.instance-card').filter(has=desktop.get_by_role('heading',name=active['name'],exact=True)).click()
                if active['status']!='running':await desktop.get_by_role('button',name='启动实例',exact=True).click()
            else:
                await desktop.get_by_role('button',name='新建酒馆实例',exact=False).click();dialog=desktop.get_by_role('dialog')
                await dialog.get_by_label('实例名称',exact=True).fill('M1 预设实验室');await dialog.get_by_label('游戏端口',exact=True).fill('18180');await dialog.get_by_role('button',name='创建、安装并启动',exact=True).click()
            await expect(desktop.locator('.instance-heading .status')).to_contain_text('运行中',timeout=180000)
            state=await desktop.evaluate("() => window.emberDesktop.invoke('state')")
            active=next(item for item in state['instances'] if item['commit'] and not item.get('recovered_from_id'))
            i=active['id'];base='http://127.0.0.1:'+str(active['port']);intents=[]
            async def capture(request):
                if request.url.endswith('/desktop-api') and request.method=='POST':
                    data=request.post_data_json
                    if data.get('method')=='createPresetRoom':intents.append(data['args'])
            desktop.on('request',capture)
            await desktop.locator('.desktop-preset-card').filter(has_text='雾港：最后一班渡船').click()
            await desktop.get_by_label('玩法房间名称',exact=True).fill('M1 桌面整套组合')
            await desktop.get_by_role('button',name='用预设开新桌',exact=True).click()
            await expect(desktop.get_by_role('heading',name='M1 桌面整套组合',exact=True)).to_be_visible()
            rooms=await desktop.evaluate("id => window.emberDesktop.invoke('rooms',{instanceId:id})",i)
            room=next(room for room in rooms if room['title']=='M1 桌面整套组合');rid=room['id']
            result=await desktop.evaluate("args => window.emberDesktop.invoke('createPresetRoom',args)",intents[-1])
            assert result['id']==rid
            report['desktop_atomic_composition_and_retry']=True
            await desktop.get_by_label('向导同伴身份',exact=True).fill('M1同伴')
            await desktop.get_by_role('button',name='生成这位同伴的密钥',exact=True).click();key=await desktop.get_by_label('向导一次性显示的密钥',exact=True).input_value();await desktop.get_by_role('button',name='隐藏密钥',exact=True).click()
            pc=await browser.new_context(viewport={'width':390,'height':844});player=await pc.new_page();player.on('pageerror',lambda error:errors.append(str(error)))
            await player.goto(base+'/?guest=1');entry=player.get_by_role('dialog');await entry.get_by_label('你的身份',exact=True).fill('M1同伴');await entry.get_by_label('验证密钥',exact=False).fill(key);await entry.get_by_role('button',name='验证并进入房间',exact=True).click();await entry.wait_for(state='hidden')
            guest_token=await player.evaluate("() => sessionStorage.getItem('ember-session')")
            me=await pc.request.get(base+'/api/auth/me',headers={'X-Ember-Session':guest_token});guest_id=(await me.json())['id']
            await desktop.get_by_label('分配角色 洛恩·灯誓',exact=True).select_option(guest_id)
            await expect(player.get_by_label('选择行动角色')).not_to_have_value('')
            await player.get_by_label('描述角色行动',exact=True).fill('我们先商量邀请上的证据，再决定下一步。');await player.get_by_role('button',name='发送',exact=True).click();await expect(player.locator('.gm-event').last).to_contain_text('不需要检定')
            report['named_guest_action_in_preset_room']=True
            # Test harness only: the preview deliberately uses synthetic BASE64,
            # never access LOCALAPPDATA or production protected credential files.
            qa=Path(state['root']).resolve();assert qa.is_relative_to(ROOT/'artifacts')
            raw=json.loads((qa/'desktop-credentials.json').read_text());accounts=json.loads(base64.b64decode(raw['encrypted']).decode());account=accounts[i]
            login=await pc.request.post(base+'/api/auth/login',data=account);assert login.ok
            oh={'X-Ember-Session':(await login.json())['token']}
            async def current():
                response=await pc.request.get(base+'/api/rooms/'+rid,headers=oh);assert response.ok;return await response.json()
            for action,identifier in [('reveal','letter'),('advance','warehouse'),('reveal','ledger'),('advance','board'),('advance','evidence')]:
                view=await current();body={'expected_revision':view['revision'],'request_key':'desktop-m1-'+action+'-'+identifier,'scene_id':view['state']['campaign']['current_scene'],('clue_id' if action=='reveal' else 'transition_id'):identifier}
                response=await pc.request.post(base+'/api/rooms/'+rid+'/campaign/'+action,headers=oh,data=body);assert response.ok,await response.text()
            complete=await current();assert complete['state']['campaign']['completed'] and complete['state']['_preset_lock']['preset']['id']=='harbor-last-ferry'
            await desktop.screenshot(path=str(OUTPUT/'01-desktop-composition.png'),full_page=True)
            await desktop.get_by_role('button',name='停止实例',exact=True).click();await expect(desktop.locator('.instance-heading .status')).to_contain_text('待启动',timeout=30000)
            await desktop.get_by_role('button',name='启动实例',exact=True).click();await expect(desktop.locator('.instance-heading .status')).to_contain_text('运行中',timeout=30000)
            restored=await current();assert restored['state']['campaign']['completed'] and restored['state']['_preset_lock']==complete['state']['_preset_lock']
            await player.reload();await player.get_by_role('heading',name='冒险现场',exact=True).wait_for()
            assert 'hbr-secret-m1' not in await player.locator('body').inner_text()
            report['ending_lock_and_guest_survive_restart']=True
            await desktop.get_by_role('button',name='停止实例',exact=True).click();await expect(desktop.locator('.instance-heading .status')).to_contain_text('待启动',timeout=30000)
            assert not errors,errors;report.update(status='passed',page_errors=errors)
        except Exception as exc:
            report.update(status='failed',error=str(exc),page_errors=errors);await desktop.screenshot(path=str(OUTPUT/'failure.png'),full_page=True);raise
        finally:
            (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2));await browser.close()


asyncio.run(main())
