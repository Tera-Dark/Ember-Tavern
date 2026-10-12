import {onMounted,onUnmounted,nextTick} from 'vue';
export function trapModalFocus(dialog:HTMLElement,close:()=>void){
 const previous=document.activeElement as HTMLElement|null;
 const controls=()=>[...dialog.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),[tabindex="0"]')].filter(el=>el.getClientRects().length);
 const key=(event:KeyboardEvent)=>{if(event.key==='Escape'){event.preventDefault();close();return;}if(event.key!=='Tab')return;const list=controls(),first=list[0],last=list.at(-1);if(!first)return;if(event.shiftKey&&(document.activeElement===first||!dialog.contains(document.activeElement))){event.preventDefault();last?.focus();}else if(!event.shiftKey&&(document.activeElement===last||!dialog.contains(document.activeElement))){event.preventDefault();first.focus();}};
 (dialog.querySelector<HTMLElement>('[autofocus]')||controls()[0])?.focus();document.addEventListener('keydown',key);
 return ()=>{document.removeEventListener('keydown',key);if(previous?.isConnected)previous.focus();};
}
export function useModalFocus(selector:string,close:()=>void,canClose:()=>boolean=()=>true){
 let previous:HTMLElement|null=null;
 function key(event:KeyboardEvent){const dialog=document.querySelector<HTMLElement>(selector);if(!dialog)return;
  if(event.key==='Escape'&&canClose()){event.preventDefault();close();return;}
  if(event.key!=='Tab')return;
  const controls=[...dialog.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),[tabindex="0"]')].filter(el=>el.getClientRects().length);
  const first=controls[0],last=controls.at(-1);if(!first)return;
  if(event.shiftKey&&(document.activeElement===first||!dialog.contains(document.activeElement))){event.preventDefault();last?.focus();}
  else if(!event.shiftKey&&(document.activeElement===last||!dialog.contains(document.activeElement))){event.preventDefault();first.focus();}
 }
 onMounted(async()=>{previous=document.activeElement as HTMLElement;await nextTick();const dialog=document.querySelector<HTMLElement>(selector);(dialog?.querySelector<HTMLElement>('[autofocus]')||dialog?.querySelector<HTMLElement>('button,input'))?.focus();document.addEventListener('keydown',key);});
 onUnmounted(()=>{document.removeEventListener('keydown',key);if(previous?.isConnected)previous.focus();});
}
