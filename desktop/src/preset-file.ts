export function presetPayload(bytes:Uint8Array,name:string):Record<string,unknown>{
  const extension=name.toLowerCase().split('.').at(-1);
  if(extension==='zip'){
    if(bytes.length>1024*1024)throw new Error('预设 ZIP 最多 1 MiB');
    return {archive_base64:Buffer.from(bytes).toString('base64')};
  }
  if(extension==='json'){
    if(bytes.length>2*1024*1024)throw new Error('规范 JSON 包最多 2 MiB');
    const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes).replace(/^\uFEFF/,''));
    if(!value||typeof value!=='object'||Array.isArray(value)||value.format!=='ember.preset-bundle/v1')throw new Error('只支持 ember.preset-bundle/v1 数据包，不执行文件或脚本');
    return {document:value};
  }
  throw new Error('只选择 ZIP 或规范 JSON 数据包');
}
