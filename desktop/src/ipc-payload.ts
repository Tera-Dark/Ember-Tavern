// Electron's structured clone rejects Vue reactive proxies. RPC is JSON-only.
export function plainRPCArgs(args:Record<string,unknown>):Record<string,unknown>{
  const text=JSON.stringify(args);
  if(!text||text.length>40000)throw new Error('请求格式错误或过长');
  const value=JSON.parse(text);
  if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('请求格式错误');
  return value;
}
