import qrcode from 'qrcode-generator';
export function guestEntryURL(value:string):string {
 if(typeof value!=='string'||value.length>256)throw new Error('入座地址无效');
 const url=new URL(value);
 if(!['http:','https:'].includes(url.protocol)||url.username||url.password||url.search||url.hash||url.pathname!=='/'||['localhost','0.0.0.0','[::1]'].includes(url.hostname)||url.hostname.startsWith('127.'))throw new Error('请使用不含凭据的 LAN 或 VPN 服务地址');
 url.search='?guest=1';return url.href;
}
export function guestEntryQR(value:string):{url:string;image:string}{
 const url=guestEntryURL(value);const qr=qrcode(0,'M');qr.addData(url);qr.make();return {url,image:qr.createDataURL(4,16)};
}
