export type Theme = 'ember'|'moonlit'|'light';
export interface Task {id:string;instance_id:string;kind:string;status:string;stage:string;percent:number;error?:string;logs:string[]}
export interface Instance {id:string;name:string;port:number;lan:boolean;channel:string;status:string;version:string;commit:string;url?:string;pid?:number;lan_urls:string[];data_path:string;task?:Task;error?:string;recovered_from_id?:string}
export interface Room {id:string;title:string;code:string;revision:number;branch:number;turn?:number;world_title?:string;is_owner:boolean;ai_mode:string;members:any[]|number;state?:any;plugins?:any[];access?:any}
export interface Invite {id:string;identity:string;enabled:boolean;key_hint:string;user_id?:string;verification_key?:string}
export interface IndexIssue {entry_id:string;legacy_id:string;name:string;reason:string;can_recover:boolean;restored_id?:string}
export interface IndexRecovery {entries:IndexIssue[];backup_name?:string;pending:number}
export interface BuildInfo {format:string;commit:string;source:string;source_dirty:boolean;desktop_version:string;launcher_version:string;app_version:string;built_at:string}
export interface Diagnostic {id:string;label:string;status:'passed'|'warning'|'action'|'unknown';detail:string}
export interface Starter {id:'harbor'|'frontier';name:string;category:string;description:string;first_action:string;world_title:string;rule_system:string;suggested_players:string;ai_mode:'demo';label:string;external_calls:boolean}
export interface State {launcher_version:string;platform:string;root:string;instances:Instance[];tasks:Task[];index_recovery?:IndexRecovery;bundled_commit?:string;build?:BuildInfo}
export type RPCMethod='state'|'recoverIndex'|'diagnostics'|'starterWorlds'|'assignCharacter'|'createInstance'|'instanceAction'|'configureInstance'|'settings'|'saveSettings'|'rooms'|'createRoom'|'room'|'roomAction'|'guestInvites'|'issueGuest'|'revokeGuest'|'installPlugin'|'openGame'|'external'|'clipboard'|'window';
export interface Bridge {kind?:string;invoke<T=any>(method:RPCMethod,args?:Record<string,any>):Promise<T>}
declare global {interface Window {emberDesktop?:Bridge; emberGame?:{session():Promise<{token:string}>}}}
