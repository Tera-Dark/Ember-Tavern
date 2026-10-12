import type {State,Instance,Diagnostic} from '../types';
const statuses=new Set(['running','ready','not_installed','busy','error']);
const kinds=new Set(['install','start','stop','update','switch','plugin-install','backup','restore']);
const phases=new Set(['preparing','resolving','runtime','source','dependencies','validating','committing','cancelling','cancelled','failed','completed','interrupted']);
const errors=new Set(['cancelled','timeout','interrupted','operation_failed']);
const version=(value:unknown)=>typeof value==='string'&&/^\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?$/.test(value)?value:'unknown';
/** A whitelist, never a clone/redaction of the full private state or logs. */
export function diagnosticReport(state:State,instance:Instance,checks:Diagnostic[],settings:Record<string,unknown>){
 return {
  format:'ember.desktop-diagnostics/v1',generatedAt:new Date().toISOString(),
  build:{desktop:version(state.build?.desktop_version),engine:version(state.launcher_version),app:version(instance.version),source:state.build?.commit&&/^[a-f0-9]{40}$/.test(state.build.commit)?state.build.commit:'unknown',dirty:typeof state.build?.source_dirty==='boolean'?state.build.source_dirty:null},
  service:{status:statuses.has(instance.status)?instance.status:'unknown',lan:instance.lan===true,detectedAddresses:Array.isArray(instance.lan_urls)?instance.lan_urls.length:0},
  configuration:{decisionKey:settings.DECISION_API_KEY_configured===true,knowledgeKey:settings.GEMINI_API_KEY_configured===true,voiceKey:settings.TTS_API_KEY_configured===true,desktopProfile:settings._desktop_profile_active===true},
  checks:checks.filter(c=>['environment','lan','demo','models','health','version'].includes(c.id)).map(c=>({id:c.id,status:['passed','warning','action','unknown'].includes(c.status)?c.status:'unknown'})),
  tasks:state.tasks.filter(t=>t.instance_id===instance.id).slice(-20).map(t=>({kind:kinds.has(t.kind)?t.kind:'unknown',status:['running','success','failed','cancelled'].includes(t.status)?t.status:'unknown',phase:phases.has(t.phase||'')?t.phase:'unknown',errorCode:t.error_code?errors.has(t.error_code)?t.error_code:'unknown':undefined})),
 };
}
