export type Theme = 'ember'|'moonlit'|'light';
export interface Task {id:string;instance_id:string;kind:string;status:string;stage:string;percent:number;error?:string;logs:string[]}
export interface Instance {id:string;name:string;port:number;lan:boolean;channel:string;status:string;version:string;commit:string;url?:string;pid?:number;lan_urls:string[];data_path:string;task?:Task;error?:string}
export interface Room {id:string;title:string;code:string;revision:number;branch:number;turn?:number;world_title?:string;is_owner:boolean;ai_mode:string;members:any[]|number;state?:any;plugins?:any[];access?:any}
export interface Invite {id:string;identity:string;enabled:boolean;key_hint:string;user_id?:string;verification_key?:string}
export interface State {launcher_version:string;platform:string;root:string;instances:Instance[];tasks:Task[]}
export type RPCMethod='state'|'createInstance'|'instanceAction'|'configureInstance'|'settings'|'saveSettings'|'rooms'|'createRoom'|'room'|'roomAction'|'guestInvites'|'issueGuest'|'revokeGuest'|'installPlugin'|'openGame'|'external'|'clipboard'|'window';
export interface Bridge {invoke<T=any>(method:RPCMethod,args?:Record<string,any>):Promise<T>}
declare global {interface Window {emberDesktop?:Bridge; emberGame?:{session():Promise<{token:string}>}}}
