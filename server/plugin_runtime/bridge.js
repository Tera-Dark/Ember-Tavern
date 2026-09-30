(() => {
  const channel=window.__EMBER_CHANNEL;
  const waiting=new Map(), contexts=new Set(), signals=new Set();
  let current=null,serial=0;
  function request(kind,data={}) {
    const requestId='r'+(++serial);
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{waiting.delete(requestId);reject(new Error('宿主请求超时'));},110000);
      waiting.set(requestId,{resolve,reject,timer});
      parent.postMessage({ember:1,channel,requestId,kind,...data},'*');
    });
  }
  window.addEventListener('message',e=>{
    if(e.source!==parent||e.data?.ember!==1||e.data.channel!==channel)return;
    const m=e.data;
    if(m.kind==='context'){
      current=m.data;
      for(const [key,value] of Object.entries(current.theme||{}))document.documentElement.style.setProperty(key,value);
      for(const fn of contexts){try{fn(current);}catch(error){console.error(error);}}
    } else if(m.kind==='signal'){
      for(const fn of signals){try{fn(m.data);}catch(error){console.error(error);}}
    } else if(m.kind==='reply'){
      const p=waiting.get(m.requestId);if(!p)return;clearTimeout(p.timer);waiting.delete(m.requestId);
      m.error?p.reject(new Error(m.error)):p.resolve(m.result);
    }
  });
  window.EmberSDK=Object.freeze({
    version:1,
    onContext(fn){contexts.add(fn);if(current)fn(current);return()=>contexts.delete(fn);},
    onSignal(fn){signals.add(fn);return()=>signals.delete(fn);},
    getContext(){return current;},
    invoke(action,payload={},target){return request('invoke',{action,payload,target});},
    signal(name,payload={},target){parent.postMessage({ember:1,channel,kind:'signal',name,payload,target},'*');},
    notify(message,kind='success'){parent.postMessage({ember:1,channel,kind:'notify',message,level:kind},'*');},
    speak(text,options={}){return request('speak',{text,options});},
    stopSpeech(){return request('stopSpeech');},
    asset(assetId){return request('asset',{assetId});},
    downloadAsset(assetId){return request('downloadAsset',{assetId});},
    audio(assetId){return request('audio',{assetId});},
    downloadAudio(assetId){return request('downloadAudio',{assetId});}
  });
  parent.postMessage({ember:1,channel,kind:'ready'},'*');
})();
