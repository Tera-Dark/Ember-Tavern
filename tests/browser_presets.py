"""Real two-browser M1: data ZIP import, private library, graph, rewind and UI HUD.
Install the reviewed campaign-compass UI fixture before starting the host.
No paid providers or human playtest claims.
"""
import argparse
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import secrets
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from playwright.async_api import async_playwright,expect
from server.presets.codec import load_folder,parse_envelope,archive_bytes
from server.plugin_runtime.integrity import package_hash

ROOT=Path(__file__).resolve().parent.parent


async def run(base,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    suffix=secrets.token_hex(4);report={'paid_calls':False,'human_playtest':False};errors=[];console=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=os.getenv('EMBER_CHROMIUM_PATH'),headless=True,args=['--no-sandbox'])
        hc=await browser.new_context(viewport={'width':1440,'height':1040});pc=await browser.new_context(viewport={'width':390,'height':844})
        async def register(context,name):
            response=await context.request.post(base+'/api/auth/register',data={'username':name,'display_name':name,'password':'m1-fixture-password'})
            assert response.status==201,await response.text()
            value=await response.json();await context.add_init_script('if(window===window.top)sessionStorage.setItem("ember-session",'+json.dumps(value['token'])+');')
            return value,{'X-Ember-Session':value['token']}
        owner,oh=await register(hc,'m1_host_'+suffix);friend,ph=await register(pc,'m1_friend_'+suffix)
        host=await hc.new_page();player=await pc.new_page()
        for page in (host,player):
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.on('console',lambda message:console.append(message.text) if message.type=='error' else None)
        try:
            await host.goto(base)
            await host.get_by_role('heading',name='玩法预设库',exact=True).wait_for()
            await host.locator('.gameplay-card').filter(has=host.get_by_role('heading',name='雾港：最后一班渡船',exact=True)).click()
            await host.get_by_label('预设房间名称',exact=True).fill('M1 一场可收束的调查 '+suffix)
            await host.get_by_role('button',name='用此预设开新桌',exact=True).click()
            await host.get_by_role('heading',name='冒险现场',exact=True).wait_for()
            rid=host.url.rsplit('/',1)[1]
            async def state(headers=oh):
                response=await hc.request.get(base+'/api/rooms/'+rid,headers=headers);assert response.ok,await response.text();return await response.json()
            initial=await state();assert len(initial['state']['characters'])==4 and initial['state']['schema_version']==2
            assert initial['state']['_preset_lock']['preset']['id']=='harbor-last-ferry'
            await pc.request.post(base+'/api/rooms/join',headers=ph,data={'code':initial['code']})
            await player.goto(base+'/room/'+rid)
            await player.get_by_role('heading',name='冒险现场',exact=True).wait_for()
            await host.get_by_role('button',name='剧本与线索',exact=True).click()
            # Mobile navigation does not expose private source; API checks it too.
            public=await state(ph);assert '_scenario' not in public['state'] and 'hbr-secret-m1' not in json.dumps(public)
            opening=initial['events'][0]['id']
            await host.get_by_role('button',name='揭示 湿透的邀请',exact=True).click()
            await host.get_by_role('button',name='推进：先到仓库核对邀请',exact=True).click()
            await expect(host.locator('.gm-guidance')).to_contain_text('hbr-secret-m1')
            assert 'hbr-secret-m1' not in await player.locator('body').inner_text()
            await host.get_by_role('button',name='揭示 货单的空行',exact=True).click()
            await host.get_by_role('button',name='推进：带着证据回到渡船',exact=True).click()
            await host.get_by_role('button',name='推进：用货单证据促成共同决定',exact=True).click()
            await expect(host.locator('.campaign-panel')).to_contain_text('已收束')
            complete=await state();assert complete['state']['campaign']['completed']
            await host.screenshot(path=str(output/'01-ending.png'),full_page=True)
            response=await hc.request.post(base+'/api/rooms/'+rid+'/rollback',headers=oh,data={'expected_revision':complete['revision'],'request_key':'rewind-'+suffix,'target_event_id':opening,'reason':'M1 自动化回档验收'})
            assert response.ok,await response.text()
            await expect(host.locator('.campaign-heading')).to_contain_text('第一幕 · 雨中的码头')
            restored=await state(ph);assert restored['state']['campaign']['current_scene']=='dock' and not restored['state']['campaign']['revealed_clues']
            report.update(bundled_atomic_create=True,gm_only_projection=True,host_confirmed_ending=True,scene_and_clues_rewind=True)
            await host.get_by_role('button',name='冒险大厅',exact=True).click()
            value=deepcopy(load_folder(ROOT/'presets/harbor-last-ferry').envelope());manifest=json.loads(value['files']['preset.json'])
            identity='browser-story-'+suffix;manifest['metadata'].update(id=identity,name='社区罗盘样板 '+suffix)
            manifest['plugins'].append({'id':'campaign-compass','version':'1.0.0','sha256':package_hash(ROOT/'templates/campaign-compass'),'required':True,'enabled':True})
            value['files']['preset.json']=json.dumps(manifest,ensure_ascii=False,indent=2)+'\n';parsed=parse_envelope(value)
            await host.get_by_label('选择玩法预设包',exact=True).set_input_files({'name':'community-story.zip','mimeType':'application/zip','buffer':archive_bytes(parsed)})
            await host.get_by_role('heading',name='导入预览 · 社区罗盘样板 '+suffix,exact=True).wait_for()
            before=await hc.request.get(base+'/api/presets',headers=oh);assert all(entry['id']!=identity for entry in (await before.json())['entries'])
            await host.get_by_label('确认只导入数据并已检查许可',exact=True).check()
            await host.get_by_role('button',name='确认导入预设数据',exact=True).click()
            peer=await pc.request.get(base+'/api/presets',headers=ph);assert all(entry['id']!=identity for entry in (await peer.json())['entries'])
            await expect(host.locator('.chosen-preset')).to_contain_text(parsed.package_hash[:16])
            await host.get_by_label('预设房间名称',exact=True).fill('社区独立 UI 验收 '+suffix)
            await host.get_by_role('button',name='用此预设开新桌',exact=True).click()
            await host.get_by_role('heading',name='冒险现场',exact=True).wait_for();rid=host.url.rsplit('/',1)[1]
            created=await state();assert created['state']['_preset_lock']['package_hash']==parsed.package_hash
            await host.get_by_role('button',name='剧本罗盘',exact=False).click()
            iframe=host.frame_locator('iframe').first
            await iframe.get_by_role('heading',name='第一幕 · 雨中的码头',exact=True).wait_for()
            await host.get_by_role('button',name='剧本与线索',exact=True).click()
            await host.get_by_role('button',name='揭示 湿透的邀请',exact=True).click();await host.get_by_role('button',name='推进：先到仓库核对邀请',exact=True).click()
            await host.get_by_role('button',name='剧本罗盘',exact=False).click()
            await iframe.get_by_role('heading',name='第二幕 · 仓库的空行',exact=True).wait_for()
            assert 'hbr-secret-m1' not in await iframe.locator('body').inner_text()
            assert '货单的空行' not in await iframe.locator('body').inner_text() # not yet revealed
            report.update(preview_no_write_confirmed_zip_import=True,private_library_is_account_scoped=True,independent_readonly_hud=True,hud_has_no_gm_or_future_clues=True)
            await host.screenshot(path=str(output/'02-community-hud.png'),full_page=True)
            export=await hc.request.get(base+'/api/presets/'+parsed.package_hash+'/export',headers=oh);assert export.ok
            from server.presets.codec import parse_archive
            assert parse_archive(await export.body()).package_hash==parsed.package_hash
            await host.get_by_role('button',name='剧本与线索',exact=True).click()
            await host.set_viewport_size({'width':390,'height':844})
            await expect(host.locator('.campaign-panel')).to_be_visible()
            assert not await host.evaluate('() => document.documentElement.scrollWidth > innerWidth')
            report['mobile_no_horizontal_overflow']=True
            await host.screenshot(path=str(output/'03-mobile-campaign.png'),full_page=True)
            assert not errors,errors;assert not console,console
            report.update(status='passed',page_errors=errors,console_errors=console)
        except Exception as exc:
            report.update(status='failed',error=str(exc),page_errors=errors,console_errors=console)
            await host.screenshot(path=str(output/'failure.png'),full_page=True)
            raise
        finally:
            (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False,indent=2));await browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--base-url',default='http://127.0.0.1:8000');parser.add_argument('--screenshots',default='artifacts/browser-presets');args=parser.parse_args()
    asyncio.run(run(args.base_url,args.screenshots))
