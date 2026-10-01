import React, {useState} from 'react';
import {Copy, Link, Users, LockKeyhole, RotateCcw, UserMinus, LogOut, Info, X} from 'lucide-react';
import {Modal, Button} from '../components/ui.jsx';

export function InviteModal({room, user, busy, mutate, onClose, onLeave, notify}) {
  const invite = location.origin + '/?join=' + room.code;
  const [removing, setRemoving] = useState(null), [leaving, setLeaving] = useState(false);
  const localOnly = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  const accepting = room.access?.accepting_players !== false;
  async function copy(text) {
    try {await navigator.clipboard.writeText(text); notify('已复制，可以发给同伴');}
    catch {notify('浏览器不允许自动复制，请选中下方文字手动复制', 'error');}
  }
  return <Modal title="把同伴请到桌边" subtitle="大家访问同一台服务器；邀请码不能跨服务器或独立实例使用。" onClose={onClose} wide>
    <div className="invite-content"><span className="eyebrow">ROOM INVITATION</span><div className="invite-code">{room.code}</div><span className={'badge ' + (accepting ? 'green' : '')}>{accepting ? '允许新成员加入' : '新成员加入已暂停'} · {room.members.length} / {room.access?.member_limit || 12} 位成员</span>
      <Button className="primary full" icon={Copy} onClick={() => copy(room.code)}>复制邀请码</Button><label>或分享加入链接<input readOnly value={invite} onFocus={e => e.target.select()}/></label><Button className="outline full" icon={Link} onClick={() => copy(invite)}>复制邀请链接</Button>
      {localOnly && <div className="info-box small"><Info size={17}/><p>当前链接只适用于房主本机。局域网同伴请先访问这台电脑的局域网 IP（如 http://192.168.1.20:8000），再输入邀请码。无需每人启动一份服务。</p></div>}
      <p><Users size={14}/>加入后，房主在「角色档案」中为玩家分配角色。玩家只能操控自己的角色。</p>
      {room.is_owner && <section className="invite-management"><h3><LockKeyhole size={16}/>房主邀请管理</h3><div className="row"><Button className="outline compact" disabled={busy} icon={LockKeyhole} onClick={() => mutate('/invitation', {accepting_players: !accepting})}>{accepting ? '暂停新成员加入' : '重新开放加入'}</Button><Button className="outline compact" disabled={busy} icon={RotateCcw} onClick={() => mutate('/invitation', {accepting_players: accepting, rotate_code: true})}>重置邀请码</Button></div><small>重置立即使旧码失效；现有成员仍可返回。邀请状态、成员与操控权不随剧情回档。</small></section>}
      {room.ai_mode==='live'&&<div className="info-box small"><Info size={17}/><p>本房已启用真实模型。受邀成员的行动也会调用部署者配置的服务；当前没有费用硬额度，请只邀请可信同伴。</p></div>}<section className="invite-members"><h3>这张桌子的成员</h3>{room.members.map(member => <div key={member.id}><span className={'status-dot ' + (member.online ? '' : 'muted-dot')}/><b>{member.display_name}{member.id === user.id ? '（你）' : ''}</b><small>{member.role === 'host' ? '房主' : '玩家'}</small>{room.is_owner && member.role !== 'host' && <button className="text-button" disabled={busy} aria-label={'移除成员 ' + member.display_name} onClick={() => setRemoving(member)}><UserMinus size={13}/>移除</button>}</div>)}</section>
      {removing && <div className="member-confirm"><b>移除「{removing.display_name}」？</b><p>会断开其实时连接并解除角色分配。不是永久封禁；若不希望重新加入，请同时暂停邀请或重置邀请码。</p><div><Button className="ghost compact" onClick={() => setRemoving(null)}>取消</Button><Button className="danger compact" disabled={busy} onClick={async () => {if (await mutate('/members/' + removing.id + '/remove')) setRemoving(null);}}>确认移除成员</Button></div></div>}
      {!room.is_owner && (leaving ? <div className="member-confirm"><b>离开当前房间？</b><p>你的角色会解除分配。已有故事记录不会删除；再次加入需要有效邀请。</p><div><Button className="ghost compact" onClick={() => setLeaving(false)}>取消</Button><Button className="danger compact" disabled={busy} onClick={onLeave}>确认离开</Button></div></div> : <Button className="ghost full" icon={LogOut} disabled={busy} onClick={() => setLeaving(true)}>离开房间</Button>)}
    </div>
  </Modal>;
}
