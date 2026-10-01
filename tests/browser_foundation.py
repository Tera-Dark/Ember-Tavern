"""Real two-browser creator, privacy, theme, SDK and room-access acceptance.

Uses only demo providers. Install the reviewed dice-tray example before running.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets

from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parent.parent


def template(kind):
    return json.loads((ROOT / 'templates' / kind / f'{kind}.json').read_text(encoding='utf-8'))


async def run(base_url, screenshots=None):
    output = Path(screenshots) if screenshots else None
    if output:
        output.mkdir(parents=True, exist_ok=True)
    errors, console_errors, report = [], [], {}
    suffix = secrets.token_hex(4)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True, args=['--no-sandbox'],
                                                   executable_path=os.getenv('EMBER_CHROMIUM_PATH'))
        host_context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        player_context = await browser.new_context(viewport={'width': 1440, 'height': 1000})
        # Simulate an access gateway reserving/stripping Authorization headers.
        # WebSocket credentials remain in the first authenticated frame.
        async def proxy_headers(route):
            await route.continue_(headers={key:value for key,value in route.request.headers.items() if key.lower() != 'authorization'})
        for context in (host_context,player_context):
            await context.route('**/api/**',proxy_headers)
        host, player = await host_context.new_page(), await player_context.new_page()
        for page in (host, player):
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('console', lambda message: console_errors.append(message.text) if message.type == 'error' else None)

        async def register(context, username, display_name):
            response = await context.request.post(base_url + '/api/auth/register', data={
                'username': username, 'display_name': display_name, 'password': 'foundation-test-password'})
            assert response.ok, await response.text()
            return await response.json()

        owner = await register(host_context, 'found_host_' + suffix, '创作验收房主')
        friend = await register(player_context, 'found_friend_' + suffix, '桌边同伴')
        await host_context.add_init_script('if(window === window.top) sessionStorage.setItem("ember-session",' + json.dumps(owner['token']) + ');')
        await player_context.add_init_script('if(window === window.top) sessionStorage.setItem("ember-session",' + json.dumps(friend['token']) + ');')
        owner_headers = {'Authorization': 'Bearer ' + owner['token']}
        friend_headers = {'Authorization': 'Bearer ' + friend['token']}
        response = await host_context.request.post(base_url + '/api/rooms', headers=owner_headers,
                                                  data={'title': '生态地基验收 · ' + suffix})
        assert response.ok, await response.text()
        initial = await response.json()
        rid = initial['id']
        response = await player_context.request.post(base_url + '/api/rooms/join', headers=friend_headers,
                                                    data={'code': initial['code']})
        assert response.ok
        await host.goto(base_url + '/room/' + rid, wait_until='networkidle')
        await player.goto(base_url + '/room/' + rid, wait_until='networkidle')
        await host.get_by_role('heading', name='冒险现场', exact=True).wait_for()
        await player.get_by_role('heading', name='冒险现场', exact=True).wait_for()

        async def state(headers):
            response = await host_context.request.get(base_url + '/api/rooms/' + rid, headers=headers)
            assert response.ok, await response.text()
            return await response.json()

        async def upload(page, kind, document):
            dialog = page.get_by_role('dialog')
            await dialog.get_by_label('选择创作 JSON 文件').set_input_files({
                'name': kind + '.json', 'mimeType': 'application/json',
                'buffer': json.dumps(document, ensure_ascii=False).encode()})
            await dialog.locator('.import-summary').wait_for()
            return dialog

        await host.get_by_role('button', name='创作工坊', exact=True).click()
        await host.get_by_role('heading', name='把一个世界，交给下一张桌。').wait_for()
        if output:
            await host.screenshot(path=str(output / 'creator-workbench.png'), full_page=True)
        world_card = host.locator('.creator-card').filter(has=host.get_by_role('heading', name='世界书', exact=True))
        await world_card.get_by_role('button', name='校验并导入', exact=True).click()
        book = template('worldbook')
        book['world']['title'] = '创作导入的新世界'
        book['world']['lore'][2]['content'] = 'SERVERONLYSECRET' + suffix + ' 守塔人在地窖，但不直接告诉玩家。'
        dialog = await upload(host, 'worldbook', book)
        await dialog.get_by_label('导入方式', exact=True).select_option('replace')
        await expect(dialog.get_by_role('button', name='确认导入', exact=True)).to_be_disabled()
        assert (await state(owner_headers))['revision'] == initial['revision']
        await dialog.get_by_role('checkbox').check()
        await dialog.get_by_role('button', name='确认导入', exact=True).click()
        await dialog.wait_for(state='hidden')
        await expect(host.get_by_role('main').get_by_role('heading', name='创作导入的新世界', exact=True)).to_be_visible()
        await player.get_by_role('button', name='世界书', exact=False).first.click()
        await expect(player.get_by_role('main').get_by_role('heading', name='创作导入的新世界', exact=True)).to_be_visible()
        assert not await player.get_by_text('主持秘密 · 守塔人的去向', exact=True).count()
        public_state = await state(friend_headers)
        assert 'SERVERONLYSECRET' not in json.dumps(public_state)
        report['preview_no_write_then_confirmed_import'] = True
        report['gm_only_not_delivered_to_player'] = True

        await host.get_by_role('button', name='主持设置', exact=False).first.click()
        await host.get_by_label('测试世界书激活').fill('我调查地窖里的守塔人')
        await host.get_by_role('button', name='预览', exact=True).click()
        await expect(host.locator('.context-preview-result')).to_contain_text('主持秘密 · 守塔人的去向')
        await expect(host.locator('.context-preview-result')).to_contain_text('规则优先')
        report['context_inspector'] = True
        await host.locator('.context-preview-result').scroll_into_view_if_needed()
        if output:
            await host.screenshot(path=str(output / 'context-inspector.png'), full_page=True)

        await host.get_by_role('button', name='角色档案', exact=False).first.click()
        await host.get_by_role('button', name='导入角色卡', exact=True).click()
        card = template('character')
        card['character'].update(name='新朋友', gm_notes='CHARACTERSECRET' + suffix,
                                 extensions={'example.extra/v1': {'rank': 3}})
        dialog = await upload(host, 'character', card)
        await dialog.get_by_role('checkbox').check()
        await dialog.get_by_role('button', name='确认导入', exact=True).click()
        await dialog.wait_for(state='hidden')
        await expect(host.get_by_role('main').get_by_role('heading', name='新朋友', exact=True)).to_be_visible()
        after_import = await state(owner_headers)
        char = after_import['state']['characters'][-1]
        assert char['assigned_to'] is None
        await host.get_by_label('分配角色 新朋友').select_option(friend['user']['id'])
        await player.get_by_role('button', name='角色档案', exact=False).first.click()
        await expect(player.get_by_role('main').get_by_role('heading', name='新朋友', exact=True)).to_be_visible()
        assert 'CHARACTERSECRET' not in json.dumps(await state(friend_headers))
        await host.get_by_role('button', name='编辑角色 新朋友', exact=True).click()
        dialog = host.get_by_role('dialog')
        await dialog.get_by_label('人物简介', exact=True).fill('编辑角色不会清空扩展字段。')
        await dialog.get_by_role('button', name='保存角色记录', exact=True).click()
        await dialog.wait_for(state='hidden')
        assert (await state(owner_headers))['state']['characters'][-1]['extensions']['example.extra/v1']['rank'] == 3
        exported = await host_context.request.get(base_url + f'/api/rooms/{rid}/content/characters/{char["id"]}/export', headers=owner_headers)
        assert exported.ok
        exported_card = await exported.json()
        assert exported_card['format'] == 'ember.character/v1' and 'assigned_to' not in exported_card['character']
        report['character_import_assignment_export'] = True
        report['editor_preserves_extension_data'] = True

        await host.get_by_role('button', name='创作工坊', exact=True).click()
        theme_card = host.locator('.creator-card').filter(has=host.get_by_role('heading', name='主题包', exact=True))
        await theme_card.get_by_role('button', name='校验并应用', exact=True).click()
        dialog = await upload(host, 'theme', template('theme'))
        await dialog.get_by_role('checkbox').check()
        before_theme = await state(owner_headers)
        await dialog.get_by_role('button', name='应用个人主题', exact=True).click()
        await dialog.wait_for(state='hidden')
        assert await host.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()") == '#141923'
        assert (await state(owner_headers))['revision'] == before_theme['revision']
        assert await player.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()") == '#141a17'
        report['theme_is_local_no_story_mutation'] = True

        await host.get_by_role('button', name='模块中心', exact=True).click()
        switch = host.get_by_role('switch', name='开关 桌面骰盘', exact=True)
        await switch.click()
        await expect(switch).to_have_attribute('aria-checked', 'true')
        await host.get_by_role('button', name='桌面骰盘', exact=False).first.click()
        frame = host.frame_locator('iframe[title="插件 · 桌面骰盘"]')
        await frame.get_by_role('button', name='服务器掷骰', exact=True).wait_for()
        child = next(frame for frame in host.frames if '/plugin-frame/dice-tray' in frame.url)
        ctx = await child.evaluate('EmberSDK.getContext()')
        assert ctx['theme']['--bg'] == '#141923'
        assert 'SERVERONLYSECRET' not in json.dumps(ctx) and 'CHARACTERSECRET' not in json.dumps(ctx)
        assert await child.evaluate("() => {try{return parent.document.title}catch(error){return 'blocked'}}") == 'blocked'
        assert owner['token'] not in json.dumps(ctx)
        before_dice = await state(owner_headers)
        await frame.get_by_label('骰盘表达式').fill('2d6+1')
        await frame.get_by_role('button', name='服务器掷骰', exact=True).click()
        await expect(frame.locator('.card')).to_contain_text('2d6+1 →')
        after_dice = await state(owner_headers)
        event = after_dice['events'][-1]
        assert event['type'] == 'dice' and event['payload']['source_plugin'] == 'dice-tray'
        assert event['payload']['total'] == sum(event['payload']['rolls']) + 1
        assert after_dice['state']['characters'] == before_dice['state']['characters']
        report['theme_propagates_to_isolated_plugin'] = True
        report['sdk_dice_is_server_authoritative'] = True
        report['owner_readonly_plugin_does_not_receive_secrets_or_token'] = True
        if output:
            await host.screenshot(path=str(output / 'dice-plugin.png'), full_page=True)

        await host.get_by_role('button', name='创作工坊', exact=True).click()
        await host.get_by_role('button', name='恢复默认主题', exact=True).click()
        assert await host.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()") == '#141a17'
        await host.set_viewport_size({'width': 390, 'height': 844})
        await expect(host.get_by_role('heading', name='把一个世界，交给下一张桌。')).to_be_visible()
        await host.get_by_role('button', name='世界书', exact=False).first.click()
        await expect(host.get_by_role('main').get_by_role('heading', name='创作导入的新世界', exact=True)).to_be_in_viewport()
        await host.get_by_role('button', name='创作工坊', exact=True).click()
        await host.locator('.page-scroll').evaluate('el => {el.scrollTop = 0}')
        await expect(host.get_by_role('heading', name='把一个世界，交给下一张桌。')).to_be_in_viewport()
        assert not await host.evaluate('document.documentElement.scrollWidth > innerWidth')
        if output:
            await host.screenshot(path=str(output / 'mobile-creators.png'), full_page=True)
        report['mobile_creator_no_horizontal_overflow'] = True
        world_card = host.locator('.creator-card').filter(has=host.get_by_role('heading', name='世界书', exact=True))
        await world_card.get_by_role('button', name='校验并导入', exact=True).click()
        dialog = await upload(host, 'worldbook', book)
        await dialog.locator('.import-summary').scroll_into_view_if_needed()
        await expect(dialog.locator('.import-summary')).to_be_in_viewport()
        assert not await host.evaluate('document.documentElement.scrollWidth > innerWidth')
        await dialog.get_by_role('button', name='取消', exact=True).click()
        report['mobile_navigation_and_import_preview'] = True
        await host.get_by_role('button', name='创作与开发指南', exact=True).click()
        dialog = host.get_by_role('dialog')
        await expect(dialog).to_contain_text('ember.worldbook/v1')
        await expect(dialog).to_contain_text('插件清单额外提供 authors')
        await dialog.get_by_role('button', name='关闭弹窗', exact=True).click()
        report['creator_guide_available_in_app'] = True
        await host.set_viewport_size({'width': 1440, 'height': 1000})

        await host.get_by_role('button', name='邀请同伴', exact=True).click()
        dialog = host.get_by_role('dialog')
        await expect(dialog).to_contain_text('局域网同伴')
        before_invite = await state(owner_headers)
        await dialog.get_by_role('button', name='暂停新成员加入', exact=True).click()
        await dialog.get_by_role('button', name='重新开放加入', exact=True).wait_for()
        await dialog.get_by_role('button', name='重置邀请码', exact=True).click()
        await expect(dialog.locator('.invite-code')).not_to_have_text(before_invite['code'])
        outsider = await register(host_context, 'found_other_' + suffix, '未入座的旅人')
        denied = await host_context.request.post(base_url + '/api/rooms/join', headers={'Authorization': 'Bearer ' + outsider['token']},
                                                data={'code': (await state(owner_headers))['code']})
        assert denied.status == 403
        await dialog.get_by_role('button', name='移除成员 桌边同伴', exact=True).click()
        await dialog.get_by_role('button', name='确认移除成员', exact=True).click()
        await player.get_by_role('heading', name='暂时无法入座', exact=True).wait_for()
        after_remove = await state(owner_headers)
        assert len(after_remove['members']) == 1 and after_remove['state']['characters'][-1]['assigned_to'] is None
        report['lan_hint_invite_pause_rotate_remove_and_disconnect'] = True
        assert not errors, errors
        assert not console_errors, console_errors
        report['proxy_reserved_authorization_compatible'] = True
        report.update(status='passed', browser=browser.version, page_errors=errors, console_errors=console_errors)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--screenshots')
    args = parser.parse_args()
    asyncio.run(run(args.base_url, args.screenshots))
