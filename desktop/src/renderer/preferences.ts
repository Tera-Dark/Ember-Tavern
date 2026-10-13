import type {Instance,Room} from '../types';

export interface InstancePreference {favorite:boolean;lastUsed:number;roomId?:string;roomTitle?:string}
export interface UIPreferences {version:1;instances:Record<string,InstancePreference>;dismissedTasks:string[]}
const key='ember-desktop-workspace-v1';
const identifier=/^[a-f0-9]{32}$/;
export function parsePreferences(raw:string|null):UIPreferences {
  const result:UIPreferences={version:1,instances:{},dismissedTasks:[]};
  try {
    if(!raw||raw.length>32768)return result;
    const data=JSON.parse(raw);if(data?.version!==1)return result;
    for(const [id,value] of Object.entries(data.instances||{}).slice(0,24)) {
      const item=value as any;if(!identifier.test(id)||!item||typeof item!=='object')continue;
      result.instances[id]={favorite:item.favorite===true,lastUsed:Number.isFinite(item.lastUsed)&&item.lastUsed>=0?item.lastUsed:0};
      if(identifier.test(item.roomId||''))result.instances[id].roomId=item.roomId;
      if(typeof item.roomTitle==='string')result.instances[id].roomTitle=item.roomTitle.slice(0,80);
    }
    result.dismissedTasks=Array.isArray(data.dismissedTasks)?data.dismissedTasks.filter((id:any)=>typeof id==='string'&&identifier.test(id)).slice(-100):[];
  }catch{/* UI preferences do not grant account access or change instance data. */}
  return result;
}
export function loadPreferences():UIPreferences {try{return parsePreferences(localStorage.getItem(key));}catch{return parsePreferences(null);}}
export function savePreferences(value:UIPreferences){try{localStorage.setItem(key,JSON.stringify(value));}catch{/* Storage may be unavailable. */}}
export function lastRoom(value:UIPreferences,id:string):string|undefined {
  if(value.instances[id]?.roomId)return value.instances[id].roomId;
  try {const legacy=localStorage.getItem('ember-first-table-room-'+id);return identifier.test(legacy||'')?legacy!:undefined;}catch{return undefined;}
}
export function orderInstances(instances:Instance[],preferences:UIPreferences):Instance[] {
  return [...instances].sort((a,b)=>Number(preferences.instances[b.id]?.favorite||false)-Number(preferences.instances[a.id]?.favorite||false)
    ||Number(b.status==='running')-Number(a.status==='running')
    ||(preferences.instances[b.id]?.lastUsed||0)-(preferences.instances[a.id]?.lastUsed||0)||a.name.localeCompare(b.name,'zh-CN'));
}
export function chooseContinuation(rooms:Room[],requested?:string):{room?:Room;needsSelection:boolean;missing:boolean} {
  const owned=rooms.filter(room=>room.is_owner);
  if(requested)return {room:owned.find(room=>room.id===requested),needsSelection:!owned.some(room=>room.id===requested),missing:!owned.some(room=>room.id===requested)};
  return {room:owned.length===1?owned[0]:undefined,needsSelection:owned.length>1,missing:false};
}
