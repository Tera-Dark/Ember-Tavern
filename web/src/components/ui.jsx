import React, {useEffect, useRef} from 'react';
import {Flame, Feather, Shield, Sword, BookOpen, Sparkles, Compass, X} from 'lucide-react';

export const avatarIcons = {feather:Feather, shield:Shield, sword:Sword, book:BookOpen, spark:Sparkles};

export function Mark({small=false}) {
  return <div className={'brand-mark ' + (small?'small':'')}><svg viewBox="0 0 40 40" aria-hidden="true"><path d="M22 4c2 8-4 10-2 15 3-2 4-5 5-8 9 10 12 17 6 23-6 6-17 6-22-1C3 25 9 16 13 14c-1 5 1 7 3 8 0-8 4-11 6-18Z" fill="currentColor"/><path d="M20 23c-1 5-4 6-3 10 1 4 6 5 9 1 2-4-3-7-6-11Z" fill="var(--surface)"/></svg></div>;
}
export function Avatar({character, size='', gm=false}) {
  const Icon = gm ? Flame : avatarIcons[character?.avatar] || Feather;
  return <div className={'avatar ' + size + ' ' + (gm?'gm':character?.avatar||'feather')}><Icon size={size==='large'?36:20} strokeWidth={1.5}/></div>;
}
export function D20({value,small=false}) {
  return <div className={'d20 '+(small?'small':'')}><svg viewBox="0 0 80 88" aria-hidden="true"><path d="M40 3 73 22v43L40 84 7 65V22Z M40 3 22 32l18 35 18-35 15-10 M7 22l15 10 36 0 M7 65l33 2 33-2 M22 32 7 65 M58 32l15 33 M40 67v17" fill="none" stroke="currentColor" strokeWidth="1.5"/></svg><strong>{value??'20'}</strong></div>;
}
export function Modal({title, subtitle, children, onClose, wide=false}) {
  const ref = useRef(null);
  useEffect(() => {ref.current.showModal();},[]);
  return <dialog ref={ref} className={'modal '+(wide?'wide':'')} onCancel={e=>{e.preventDefault();onClose();}} onClick={e=>{if(e.target===ref.current)onClose();}}>
    <div className="modal-inner"><div className="modal-header"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div><button className="icon-button" aria-label="关闭弹窗" onClick={onClose}><X size={20}/></button></div>{children}</div>
  </dialog>;
}
export function Button({children, icon:Icon, className='', ...props}) {
  return <button className={'button '+className} {...props}>{Icon&&<Icon size={16}/>}<span>{children}</span></button>;
}
export function Empty({icon:Icon=Compass,title,description,children}) {
  return <div className="empty"><div className="empty-icon"><Icon size={30} strokeWidth={1.3}/></div><h3>{title}</h3><p>{description}</p>{children}</div>;
}
export function Brand({onClick}) {return <button className="brand" onClick={onClick}><Mark/><span><b>余烬酒馆</b><small>EMBER TAVERN</small></span></button>;}
