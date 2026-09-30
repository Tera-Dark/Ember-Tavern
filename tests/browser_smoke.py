"""Real two-browser end-to-end test. Start the web server first.
Run: python tests/browser_smoke.py --base-url http://127.0.0.1:8000
The script creates isolated disposable test accounts and a room.
"""
import argparse
import asyncio
import json
from pathlib import Path
import secrets
import time
from playwright.async_api import async_playwright, expect

async def run(base_url, screenshots):
    suffix=secrets.token_hex(4)
    discarded='discardedtimeline'+suffix
    password='Qa_'+secrets.token_urlsafe(18)
    errors=[]
    report={}
    output=Path(screenshots) if screenshots else None
    if output:output.mkdir(parents=True,exist_ok=True)
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True,args=['--no-sandbox'])
        a=await browser.new_context(viewport={'width':1440,'height':960})
        b=await browser.new_context(viewport={'width':1280,'height':900})
        host=await a.new_page();player=await b.new_page()
        for page in (host,player):page.on('pageerror',lambda error:errors.append(str(error)))
        async def signup(page,username,display):
            await page.goto(base_url,wait_until='networkidle')
            await page.get_by_role('button',name='加入酒馆',exact=False).click()
            dialog=page.get_by_role('dialog')
            await dialog.get_by_label('用户名',exact=True).fill(username)
            await dialog.get_by_label('桌边的称呼',exact=True).fill(display)
            await dialog.get_by_label('密码',exact=True).fill(password)
            await dialog.get_by_role('button',name='注册并进入大厅',exact=True).click()
            await page.get_by_role('heading',name='晚上好，'+display,exact=False).wait_for()
        async def token(page):return await page.evaluate("() => sessionStorage.getItem('ember-session')")
        async def room_state(page,rid):
            response=await page.request.get(base_url+'/api/rooms/'+rid,headers={'Authorization':'Bearer '+await token(page)})
            assert response.ok,await response.text()
            return await response.json()
        await signup(host,'qa_host_'+suffix,'测试房主')
        await host.get_by_role('button',name='创建冒险',exact=True).click()
        await host.get_by_role('dialog').get_by_label('冒险名称',exact=True).fill('双人验收 · '+suffix)
        await host.get_by_role('button',name='创建并进入房间',exact=True).click()
        await host.get_by_role('heading',name='冒险现场',exact=True).wait_for()
        rid=host.url.rsplit('/',1)[1]
        initial=await room_state(host,rid)
        await signup(player,'qa_friend_'+suffix,'测试同伴')
        await player.get_by_role('button',name='加入房间',exact=True).click()
        await player.get_by_role('dialog').get_by_label('房间邀请码',exact=True).fill(initial['code'])
        await player.get_by_role('dialog').get_by_role('button',name='加入冒险',exact=True).click()
        await player.get_by_role('heading',name='冒险现场',exact=True).wait_for()
        await expect(host.locator('.members-heading small')).to_have_text('2 / 2 在线')
        own=await player.request.get(base_url+'/api/auth/me',headers={'Authorization':'Bearer '+await token(player)})
        player_id=(await own.json())['id']
        second_char=initial['state']['characters'][1]['id']
        await host.get_by_role('button',name='角色档案',exact=False).first.click()
        await host.get_by_label('分配角色 洛恩·灯誓').select_option(player_id)
        await expect(player.get_by_label('选择行动角色')).to_have_value(second_char)
        await host.get_by_role('button',name='冒险现场',exact=True).click()
        if output:await host.screenshot(path=str(output/'multiplayer-room.png'),full_page=True)
        action='我推开旧码头的门，并在门边记下 '+discarded
        await player.get_by_label('描述角色行动').fill(action)
        start=time.monotonic()
        await player.get_by_role('button',name='发送',exact=True).click()
        await expect(host.locator('.action-event .event-text').last).to_have_text(action)
        report['action_sync_ms']=round((time.monotonic()-start)*1000)
        await player.get_by_role('button',name='掷 d20',exact=True).wait_for()
        await player.get_by_role('button',name='掷 d20',exact=True).click()
        await player.get_by_role('button',name='掷 d20',exact=True).wait_for(state='detached')
        await player.locator('.gm-thinking').wait_for(state='hidden')
        await expect(host.locator('.dice-event')).to_have_count(1)
        await host.get_by_role('button',name='角色档案',exact=False).first.click()
        await host.get_by_role('button',name='编辑角色 洛恩·灯誓',exact=True).click()
        dialog=host.get_by_role('dialog')
        await dialog.get_by_label('当前生命',exact=True).fill('4')
        await dialog.get_by_label('压力（0–6）',exact=True).fill('3')
        await dialog.get_by_label('力量',exact=True).fill('4')
        await dialog.get_by_label('随身物品',exact=False).fill('未来道具 '+discarded)
        await dialog.get_by_role('button',name='保存角色记录',exact=True).click()
        await dialog.wait_for(state='hidden')
        await host.get_by_role('button',name='世界书',exact=False).first.click()
        await host.get_by_role('button',name='编辑世界书',exact=True).click()
        dialog=host.get_by_role('dialog')
        await dialog.get_by_label('世界名称',exact=True).fill('被撤销的未来世界')
        await dialog.get_by_role('button',name='添加条目',exact=True).click()
        await dialog.get_by_label('条目名称',exact=True).last.fill('未来线索')
        await dialog.get_by_label('内容',exact=True).last.fill(discarded+' 不应在回档后的上下文中出现。')
        await dialog.get_by_role('button',name='保存世界书',exact=True).click()
        await dialog.wait_for(state='hidden')
        changed=await room_state(host,rid)
        assert changed['state']['characters'][1]['hp']==4
        assert changed['state']['world']['title']=='被撤销的未来世界'
        await host.get_by_role('button',name='事件档案',exact=False).first.click()
        record=host.locator('.record-list article').filter(has=host.get_by_text('#1',exact=True))
        await record.get_by_role('button',name='回档',exact=True).click()
        await host.get_by_role('dialog').get_by_role('button',name='确认回档',exact=True).click()
        await host.get_by_role('dialog').wait_for(state='hidden')
        restored=await room_state(host,rid)
        assert restored['state']['world']==initial['state']['world']
        assert restored['state']['characters'][1]['hp']==initial['state']['characters'][1]['hp']
        assert restored['state']['characters'][1]['inventory']==initial['state']['characters'][1]['inventory']
        assert restored['state']['characters'][1]['attributes']==initial['state']['characters'][1]['attributes']
        assert restored['state']['characters'][1]['stress']==0
        assert restored['state']['characters'][1]['assigned_to']==player_id
        assert restored['state']['turn']==0 and restored['state']['pending_check'] is None
        assert restored['archived_count']>0 and len(restored['members'])==2
        await expect(player.locator('.system-event.rewind')).to_contain_text('后续记录已封存')
        await host.get_by_label('检索事件与世界书').fill(discarded)
        await host.get_by_role('button',name='检索',exact=True).click()
        await expect(host.get_by_role('heading',name='没有匹配的记录',exact=True)).to_be_visible()
        await host.get_by_role('button',name='封存记录',exact=False).click()
        await expect(host.locator('.record-list article').first).to_have_class('archived')
        if output:await host.screenshot(path=str(output/'archived-records.png'),full_page=True)
        async with host.expect_download() as download:
            await host.get_by_role('button',name='导出档案',exact=True).click()
        file=await download.value
        temp=Path(await file.path())
        exported=json.loads(temp.read_text())
        assert exported['format']=='ember-tavern/v1'
        assert any(not e['active'] for e in exported['all_events'])
        assert password not in temp.read_text()
        await host.get_by_role('button',name='冒险现场',exact=True).click()
        await host.get_by_role('button',name='切换明暗主题',exact=True).click()
        if output:await host.screenshot(path=str(output/'light-room.png'),full_page=True)
        await host.set_viewport_size({'width':390,'height':844})
        await expect(host.get_by_label('描述角色行动')).to_be_visible()
        overflow=await host.evaluate('() => document.documentElement.scrollWidth > innerWidth')
        assert not overflow
        await host.get_by_role('button',name='查看队伍',exact=True).click()
        await expect(host.locator('.party-panel.open')).to_be_visible()
        await host.get_by_role('button',name='关闭队伍面板',exact=True).click()
        await host.get_by_role('button',name='切换明暗主题',exact=True).click()
        if output:await host.screenshot(path=str(output/'mobile-room.png'),full_page=True)
        assert not errors,errors
        report.update({'status':'passed','accounts':2,'websocket_sync':True,'role_assignment':True,
                       'action_and_roll':True,'full_state_rollback':True,'permission_not_rewound':True,
                       'archived_memory_excluded':True,'export':True,'mobile_overflow':overflow,'page_errors':errors})
        await browser.close()
    if output:(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:8000')
    parser.add_argument('--screenshots',default=None)
    args=parser.parse_args()
    asyncio.run(run(args.base_url.rstrip('/'),args.screenshots))
