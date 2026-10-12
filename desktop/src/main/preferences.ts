import {mkdir,readFile,writeFile,rename,lstat} from 'node:fs/promises';
import {join} from 'node:path';
export interface WindowBounds{x:number;y:number;width:number;height:number}
export interface DesktopPreferences{format:'ember.desktop-preferences/v1';closeBehavior:'ask'|'tray'|'quit';openBehavior:'dashboard'|'last';bounds?:WindowBounds;maximized:boolean}
export const defaults=():DesktopPreferences=>({format:'ember.desktop-preferences/v1',closeBehavior:'ask',openBehavior:'dashboard',maximized:false});
export function parseDesktopPreferences(value:any):DesktopPreferences {
 if(!value||typeof value!=='object'||Array.isArray(value)||value.format!=='ember.desktop-preferences/v1')throw new Error('桌面偏好格式不受支持');
 if(!['ask','tray','quit'].includes(value.closeBehavior)||!['dashboard','last'].includes(value.openBehavior)||typeof value.maximized!=='boolean')throw new Error('桌面偏好无效');
 const result:DesktopPreferences={format:value.format,closeBehavior:value.closeBehavior,openBehavior:value.openBehavior,maximized:value.maximized};
 if(value.bounds!==undefined){const b=value.bounds;if(!b||!['x','y','width','height'].every(k=>Number.isInteger(b[k]))||Math.abs(b.x)>100000||Math.abs(b.y)>100000||b.width<400||b.width>16000||b.height<300||b.height>16000)throw new Error('窗口位置无效');result.bounds={x:b.x,y:b.y,width:b.width,height:b.height};}
 return result;
}
export function fitWindow(bounds:WindowBounds|undefined,areas:WindowBounds[]):WindowBounds {
 const area=areas.find(a=>bounds&&bounds.x<a.x+a.width&&bounds.x+bounds.width>a.x&&bounds.y<a.y+a.height&&bounds.y+bounds.height>a.y)||areas[0]||{x:0,y:0,width:1380,height:920};
 const width=Math.min(area.width,Math.max(Math.min(760,area.width),bounds?.width||1380)),height=Math.min(area.height,Math.max(Math.min(520,area.height),bounds?.height||920));
 return {width,height,x:Math.round(Math.min(Math.max(bounds?.x??area.x+(area.width-width)/2,area.x),area.x+area.width-width)),y:Math.round(Math.min(Math.max(bounds?.y??area.y+(area.height-height)/2,area.y),area.y+area.height-height))};
}
export class PreferencesStore{
 value=defaults();error='';private tail:Promise<void>=Promise.resolve();
 constructor(readonly root:string){}
 async load(){try{const path=join(this.root,'desktop-preferences.json'),info=await lstat(path);if(!info.isFile()||info.isSymbolicLink()||info.size>32768)throw new Error('invalid preferences file');this.value=parseDesktopPreferences(JSON.parse(await readFile(path,'utf8')));}catch(e:any){if(e.code!=='ENOENT')this.error='桌面偏好无法读取，原文件已保留。请保留 desktop-preferences.json 后检查格式；窗口使用默认设置。';}return this.snapshot();}
 snapshot(){return {...structuredClone(this.value),readOnly:!!this.error,error:this.error||undefined};}
 update(patch:Partial<DesktopPreferences>):Promise<void>{const task=this.tail.then(async()=>{if(this.error)throw new Error(this.error);const next=parseDesktopPreferences({...this.value,...patch});await mkdir(this.root,{recursive:true});const path=join(this.root,'desktop-preferences.json');await writeFile(path+'.tmp',JSON.stringify(next,null,2)+'\n',{mode:0o600});await rename(path+'.tmp',path);this.value=next;});this.tail=task.catch(()=>{});return task;}
}
