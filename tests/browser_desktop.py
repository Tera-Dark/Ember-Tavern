"""Real controller + renderer preview QA. Native Electron is covered separately on Windows."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright,expect

async def main():
    output=Path('artifacts/desktop-preview-evidence');output.mkdir(parents=True,exist_ok=True)
    report={};errors=[]
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path=os.environ.get('EMBER_CHROMIUM_PATH'),headless=True,args=['--no-sandbox'])
        page=await browser.new_page(viewport={'width':1440,'height':1000});page.on('pageerror',lambda e:errors.append(str(e)))
        await page.goto('http://127.0.0.1:8765');await expect(page.get_by_role('heading',name='把一张桌，点成一个世界。')).to_be_visible()
        await page.screenshot(path=str(output/'desktop-home.png'))
        await page.get_by_role('button',name='主题 月下',exact=True).click();await expect(page.locator('html')).to_have_attribute('data-theme','moonlit');report['theme_switch']=True
        await page.get_by_role('button',name='新建酒馆实例',exact=False).click();dialog=page.get_by_role('dialog');await dialog.get_by_label('实例名称',exact=True).fill('周末 · 雾港酒馆');await dialog.get_by_label('游戏端口',exact=True).fill('18180');await dialog.get_by_role('button',name='创建、安装并启动',exact=True).click()
        await expect(page.locator('.instance-heading .status')).to_contain_text('运行中',timeout=180000);report['real_venv_install_start']=True
        await page.screenshot(path=str(output/'desktop-instance.png'))
        await page.get_by_role('button',name='房间与同伴',exact=True).click();await page.get_by_label('房间名称',exact=True).fill('周六 · 灯塔的秘密');await page.get_by_role('button',name='创建房间',exact=True).click();await page.get_by_role('heading',name='周六 · 灯塔的秘密',exact=True).wait_for();report['host_auto_login_create_room']=True
        await page.get_by_label('同伴身份',exact=True).fill('伊芙的玩家');await page.get_by_role('button',name='生成专属密钥',exact=True).click();dialog=page.get_by_role('dialog');key=await dialog.locator('input').nth(1).input_value();await dialog.get_by_role('button',name='关闭弹窗').click()
        player=await browser.new_page(viewport={'width':390,'height':844});await player.goto('http://127.0.0.1:18180/?guest=1');guest=player.get_by_role('dialog');await guest.get_by_label('你的身份',exact=True).fill('伊芙的玩家');await guest.get_by_label('验证密钥',exact=False).fill(key);await guest.get_by_role('button',name='验证并进入房间',exact=True).click();await guest.wait_for(state='hidden');await player.get_by_role('button',name='角色档案',exact=False).first.wait_for();report['browser_guest_no_registration']=True
        await page.screenshot(path=str(output/'desktop-room.png'));await player.screenshot(path=str(output/'mobile-guest.png'))
        await page.get_by_role('button',name='插件管理',exact=True).click();switch=page.get_by_role('switch',name='开关 场景地图',exact=True);await switch.click();await expect(switch).to_have_attribute('aria-checked','true');report['plugin_toggle']=True
        await page.get_by_role('button',name='停止实例',exact=True).click();await expect(page.locator('.instance-heading .status')).to_contain_text('待启动',timeout=30000);report['stop_owned_process']=True
        await page.get_by_role('button',name='API 与配置',exact=True).click();section=page.locator('.panel').filter(has=page.get_by_role('heading',name='世界知识 · Gemini',exact=True));await section.locator('input[type=password]').fill('qa-only-not-a-real-key');await page.get_by_role('button',name='保存 API 配置',exact=True).click();await expect(section.locator('input[type=password]')).to_have_value('');await expect(section).to_contain_text('已配置');report['key_not_echoed']=True
        await page.screenshot(path=str(output/'desktop-settings.png'));assert not errors,errors;report.update(status='passed',page_errors=errors,native_window=False,paid_calls=False);(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2));await browser.close()

asyncio.run(main())
