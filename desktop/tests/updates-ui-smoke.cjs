// Isolated native-window verification; GitHub is stubbed, no installer is executed.
const {_electron,expect}=require('@playwright/test');
const {mkdtemp,writeFile,readFile}=require('node:fs/promises');const {tmpdir}=require('node:os');const {join}=require('node:path');
(async()=>{
 const root=await mkdtemp(join(tmpdir(),'ember-update-ui-'));let desktop;
 const report={status:'running',root,network:'stubbed',installation:'not executed'};
 const reportPath=process.env.EMBER_UPDATE_UI_REPORT||join(root,'report.json');
 try{
  await writeFile(join(root,'desktop-updates.json'),JSON.stringify({lastVersion:'0.2.0-beta.5',pending:{from:'0.2.0-beta.5',to:'0.2.0-beta.4',ignore:'0.2.0-beta.5'}}));
  desktop=await _electron.launch({executablePath:process.env.EMBER_SMOKE_EXE,env:{...process.env,EMBER_DESKTOP_TEST_MODE:'1',EMBER_DESKTOP_TEST_ROOT:root},timeout:60000});
  const page=await desktop.firstWindow();await page.getByRole('button',{name:'更新与版本',exact:true}).waitFor();
  const initial=await page.evaluate(()=>window.emberDesktop.invoke('state'));if(initial.build.desktop_version!=='0.2.0-beta.4')throw new Error('Incorrect local development build');report.version=initial.build.desktop_version;
  await desktop.evaluate(()=>{
   globalThis.__updateFixtureVersion='0.2.0-beta.5';const original=globalThis.fetch;
   globalThis.fetch=async(input,options)=>{
    const url=String(input);
    if(url.startsWith('https://api.github.com/repos/Tera-Dark/Ember-Tavern/releases?')){
     const versions=[globalThis.__updateFixtureVersion,'0.2.0-beta.4','0.2.0-beta.3'];
     return Response.json(versions.map(version=>{
      const tag='desktop-v'+version,name='ember-desktop-'+version+'-x64-setup.exe',base='https://github.com/Tera-Dark/Ember-Tavern/releases/download/'+tag+'/';
      return {tag_name:tag,name:'Native fixture '+version,body:'Native UI fixture notes',published_at:'2026-10-12T00:00:00Z',prerelease:true,assets:[{name,size:100,browser_download_url:base+name},{name:name+'.sha256',browser_download_url:base+name+'.sha256'}]};
     }));
    }
    if(url.startsWith('http://127.0.0.1:')&&url.endsWith('/api/releases'))return Response.json([{tag:'desktop-v0.2.0-beta.5',version:'0.2.0-beta.5',published_at:'2026-10-12T00:00:00Z'}]);
    return original(input,options);
   };
  });
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.getByRole('button',{name:'更新与版本',exact:true}).click();
  await expect(page.getByRole('heading',{name:'更新与版本',exact:true})).toBeVisible();
  await expect(page.getByText(/已保留你选择的旧版/)).toBeVisible();
  await expect(page.getByRole('button',{name:'立即更新',exact:true})).toHaveCount(0);report.rollback_suppresses_prompt=true;
  await page.getByLabel('切换桌面版本').selectOption('desktop-v0.2.0-beta.3');
  await expect(page.getByRole('button',{name:'安装所选版本并重启',exact:true})).toBeEnabled();report.history_selection=true;
  await desktop.evaluate(()=>{globalThis.__updateFixtureVersion='0.2.0-beta.6';});
  await page.getByRole('button',{name:'检查 GitHub 更新',exact:true}).click();
  await expect(page.getByText('发现新版 0.2.0-beta.6',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'立即更新',exact:true})).toBeEnabled();report.new_release_alerts=true;
  const state=await page.evaluate(()=>window.emberDesktop.invoke('state'));if(!state.desktop_updates.available||state.desktop_updates.suppressed)throw new Error('New release incorrectly suppressed');
  await page.screenshot({path:reportPath+'.png',fullPage:true});
  if(errors.length)throw new Error(errors.join('\n'));report.page_errors=errors;report.status='passed';
 }catch(error){report.status='failed';report.error=String(error);throw error;}
 finally{
  if(desktop)await desktop.close();
  await writeFile(reportPath,JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }
})().catch(error=>{console.error(error);process.exitCode=1;});
