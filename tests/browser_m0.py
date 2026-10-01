"""Real controller + Go + isolated Python host, desktop renderer + phone guest.

Not a native Electron / DPAPI / human playtest. Use --seed before preview startup
on a fresh artifacts/desktop-preview directory. No paid model / TTS calls.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright, expect

ROOT=Path(__file__).resolve().parent.parent
QA=Path(os.environ.get('EMBER_DESKTOP_PREVIEW_ROOT',str(ROOT/'artifacts/desktop-preview'))).resolve()
assert QA.is_relative_to(ROOT/'artifacts'), 'QA data must be inside ignored artifacts' 
OUTPUT=ROOT/'artifacts/desktop-m0-evidence'


def seed():
    QA.mkdir(parents=True,exist_ok=True)
    assert not (QA/'launcher.json').exists(), 'Do not overwrite an existing preview index'
    old={'id':'weekend-legacy','name':'旧目录试玩备份','port':18281,'channel':'bundled','lan':False,'private_extra':'qa-evidence-do-not-echo'}
    (QA/'launcher.json').write_text(json.dumps({'schema':1,'instances':[old]},ensure_ascii=False),encoding='utf-8')
    data=QA/'instances/weekend-legacy/data';data.mkdir(parents=True,exist_ok=True)
    (data/'keep.txt').write_text('original QA data must survive',encoding='utf-8')


async def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    report={'native_window':False,'windows_encryption_tested':False,'paid_calls':False,'human_playtest':False}
    errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=os.environ.get('EMBER_CHROMIUM_PATH'),headless=True,args=['--no-sandbox'])
        context=await browser.new_context(viewport={'width':1440,'height':1080})
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            await page.goto('http://127.0.0.1:8765')
            await expect(page.get_by_role('heading',name='把一张桌，点成一个世界。',exact=True)).to_be_visible()
            await expect(page.locator('.recovery-panel')).to_contain_text('1 条待处理')
            await page.screenshot(path=str(OUTPUT/'01-home-recovery.png'))
            await page.get_by_role('button',name='新建酒馆实例',exact=False).click()
            dialog=page.get_by_role('dialog')
            await dialog.get_by_label('实例名称',exact=True).fill('M0 周末合作酒馆')
            await dialog.get_by_label('游戏端口',exact=True).fill('18180')
            await dialog.get_by_role('button',name='创建、安装并启动',exact=True).click()
            await expect(page.locator('.instance-heading .status')).to_contain_text('运行中',timeout=180000)
            await expect(page.get_by_role('heading',name='开好第一桌，也能继续上一场。',exact=True)).to_be_visible()
            await page.locator('input[value=frontier]').check()
            await page.get_by_label('向导房间名称',exact=True).fill('M0 边境合作试玩')
            await page.get_by_role('button',name='以演示创建新房间',exact=True).click()
            await expect(page.get_by_role('heading',name='M0 边境合作试玩',exact=True)).to_be_visible()
            report['real_install_wizard_starter']=True
            state=await page.evaluate("() => window.emberDesktop.invoke('state')")
            instance=next(item for item in state['instances'] if item['name']=='M0 周末合作酒馆')
            instance_id=instance['id']
            rooms=await page.evaluate("id => window.emberDesktop.invoke('rooms',{instanceId:id})",instance_id)
            assert len(rooms)==1 and rooms[0]['ai_mode']=='demo'
            room_id=rooms[0]['id']
            await page.get_by_label('向导同伴身份',exact=True).fill('旅伴阿禾')
            await page.get_by_role('button',name='生成这位同伴的密钥',exact=True).click()
            key=await page.get_by_label('向导一次性显示的密钥',exact=True).input_value()
            assert key not in await page.evaluate('() => JSON.stringify(localStorage)')
            assert key not in page.url
            await page.get_by_role('button',name='隐藏密钥',exact=True).click()
            player_context=await browser.new_context(viewport={'width':390,'height':844})
            player=await player_context.new_page();player.on('pageerror',lambda e:errors.append(str(e)))
            await player.goto('http://127.0.0.1:18180/?guest=1')
            entry=player.get_by_role('dialog')
            await entry.get_by_label('你的身份',exact=True).fill('旅伴阿禾')
            await entry.get_by_label('验证密钥',exact=False).fill(key)
            await entry.get_by_role('button',name='验证并进入房间',exact=True).click()
            await entry.wait_for(state='hidden')
            await player.get_by_role('button',name='角色档案',exact=False).first.wait_for()
            guest_token=await player.evaluate("() => sessionStorage.getItem('ember-session')")
            me=await player.request.get('http://127.0.0.1:18180/api/auth/me',headers={'X-Ember-Session':guest_token})
            guest_id=(await me.json())['id']
            await page.get_by_label('分配角色 洛恩·灯誓',exact=True).select_option(guest_id)
            await expect(player.get_by_label('选择行动角色')).to_have_value(await page.evaluate("async args => (await window.emberDesktop.invoke('room',args)).state.characters[1].id",{'instanceId':instance_id,'roomId':room_id}))
            report['phone_guest_and_wizard_assignment']=True
            report['key_not_in_url_or_storage']=True
            await page.screenshot(path=str(OUTPUT/'02-wizard-party.png'),full_page=True)
            await player.get_by_label('描述角色行动').fill('我们先商量黑马和邮袋的线索，再决定探索路线。')
            await player.get_by_role('button',name='发送',exact=True).click()
            await expect(player.locator('.gm-event').last).to_contain_text('不需要检定',timeout=20000)
            report['guest_completed_demo_action']=True
            await player.screenshot(path=str(OUTPUT/'03-phone-play.png'),full_page=True)
            await page.get_by_role('button',name='实例概览',exact=True).click()
            await page.get_by_role('button',name='运行本机自检',exact=True).click()
            await expect(page.locator('.diagnostic-list')).to_contain_text('本机健康检查通过')
            await expect(page.locator('.diagnostic-list')).to_contain_text('密钥')
            report['local_no_paid_diagnostics']=True
            await page.screenshot(path=str(OUTPUT/'04-local-checks.png'),full_page=True)
            await page.get_by_role('button',name='停止实例',exact=True).click()
            await expect(page.locator('.instance-heading .status')).to_contain_text('待启动',timeout=30000)
            await page.get_by_role('button',name='启动实例',exact=True).click()
            await expect(page.locator('.instance-heading .status')).to_contain_text('运行中',timeout=30000)
            await page.get_by_role('button',name='开桌向导',exact=True).click()
            await expect(page.get_by_role('heading',name='M0 边境合作试玩',exact=True)).to_be_visible()
            assert await page.get_by_label('向导一次性显示的密钥',exact=True).count()==0
            again=await page.evaluate("id => window.emberDesktop.invoke('rooms',{instanceId:id})",instance_id)
            assert len(again)==1 and again[0]['id']==room_id and again[0]['turn']==1
            await player.reload()
            await player.get_by_role('button',name='角色档案',exact=False).first.wait_for()
            me=await player.request.get('http://127.0.0.1:18180/api/auth/me',headers={'X-Ember-Session':guest_token})
            assert (await me.json())['id']==guest_id
            report['restart_continues_same_room_and_guest']=True
            await page.get_by_role('button',name='停止实例',exact=True).click()
            await expect(page.locator('.instance-heading .status')).to_contain_text('待启动',timeout=30000)
            await page.locator('.brand').click()
            page.once('dialog',lambda dialog:asyncio.create_task(dialog.accept()))
            await page.get_by_role('button',name='复制恢复',exact=True).click()
            await expect(page.locator('.instance-heading h2')).to_have_text('旧目录试玩备份')
            state=await page.evaluate("() => window.emberDesktop.invoke('state')")
            assert state['index_recovery']['pending']==0
            assert 'qa-evidence-do-not-echo' not in json.dumps(state)
            recovered=next(item for item in state['instances'] if item.get('recovered_from_id')=='weekend-legacy')
            assert (Path(recovered['data_path'])/'keep.txt').read_text()=='original QA data must survive'
            assert (QA/'instances/weekend-legacy/data/keep.txt').read_text()=='original QA data must survive'
            backup=QA/'index-backups'/state['index_recovery']['backup_name']
            assert 'qa-evidence-do-not-echo' in backup.read_text()
            assert recovered['commit']==''
            report['visible_copy_recovery_original_preserved']=True
            await page.locator('.brand').click()
            await page.screenshot(path=str(OUTPUT/'05-recovered-home.png'),full_page=True)
            assert not errors,errors
            report.update(status='passed',page_errors=errors)
        except Exception as exc:
            report.update(status='failed',error=str(exc),page_errors=errors)
            await page.screenshot(path=str(OUTPUT/'failure.png'),full_page=True)
            raise
        finally:
            (OUTPUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False,indent=2))
            await browser.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--seed',action='store_true');args=parser.parse_args()
    if args.seed:seed()
    else:asyncio.run(main())
