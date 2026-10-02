import type {Diagnostic,Instance} from '../types';

/** Local checks only. This function never contacts a model/provider, generates
 * speech, changes a room, registers an account or prints configuration values. */
export async function localDiagnostics(instance:Instance,settings:Record<string,unknown>):Promise<Diagnostic[]>{
  const result:Diagnostic[]=[
    {id:'environment',label:'实例环境',status:instance.commit?'passed':'action',detail:instance.commit?'本体已安装，数据独立保存。':'请先安装本体；失败可重试，不需要删除数据。'},
    {id:'lan',label:'同伴入口',status:instance.lan&&instance.lan_urls.length?'passed':'warning',detail:!instance.lan?'当前只允许本机。需要同伴时，停止实例后开启 LAN。':instance.lan_urls.length?'已发现私有 IPv4 网卡。这不证明同伴能访问；请同伴在同一网络试开地址，并检查私有网络防火墙。':'没有发现私有 IPv4 网卡，请检查 Wi-Fi、网线或 VPN。'},
    {id:'demo',label:'演示主持',status:String(settings.ENABLE_DEMO).toLowerCase()==='false'?'action':'passed',detail:String(settings.ENABLE_DEMO).toLowerCase()==='false'?'此实例关闭了演示主持，入门向导不会偷偷切换到付费模型。':'演示主持不调用外部模型；TTS 等显式生成另计。'},
    {id:'models',label:'真实模型配置',status:'unknown',detail:settings.DECISION_API_KEY_configured&&settings.DECISION_MODEL?'单模型所需字段已配置，但密钥、模型、余额和网络均未验证。Gemini 只在显式双模型模式调用。':'可先用演示开桌。真实单模型只需要决策接口；知识顾问是双模型的可选增强，密钥不向玩家回显。'},
  ];
  if(instance.status!=='running'){
    result.unshift({id:'health',label:'游戏服务',status:'action',detail:instance.status==='busy'?'等待当前安装／启停任务完成，再检查。':'服务未运行。请启动实例后重试。'});
    return result;
  }
  try{
    const response=await fetch(`http://127.0.0.1:${instance.port}/api/health`,{signal:AbortSignal.timeout(3000),redirect:'error'});
    const health=await response.json();
    if(!response.ok||health.ok!==true||health.product!=='余烬酒馆')throw new Error('not the expected host');
    result.unshift({id:'health',label:'游戏服务',status:'passed',detail:'本机健康检查通过；未向付费服务发送请求。'});
    if(instance.channel==='bundled'&&instance.version!==health.version)result.unshift({id:'version',label:'本体版本',status:'warning',detail:'运行版本与安装记录不一致，请保留数据并停止后检查更新。'});
  }catch{
    result.unshift({id:'health',label:'游戏服务',status:'action',detail:'本机健康检查未通过。请查看任务／运行日志，确认端口未被其他程序占用。'});
  }
  return result;
}
