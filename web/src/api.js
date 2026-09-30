export const TOKEN_KEY = 'ember-session';
export function getToken() { return sessionStorage.getItem(TOKEN_KEY) || ''; }
export function setToken(token) { token ? sessionStorage.setItem(TOKEN_KEY, token) : sessionStorage.removeItem(TOKEN_KEY); }
export class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
export async function api(path, options = {}) {
  const token = getToken();
  const response = await fetch('/api' + path, {
    ...options,
    headers: {'Content-Type': 'application/json', ...(token ? {'Authorization': 'Bearer ' + token} : {}), ...options.headers},
    ...(options.body !== undefined ? {body: JSON.stringify(options.body)} : {})
  });
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    let message = data.detail || '请求失败，请重试';
    if (Array.isArray(message)) message = '请检查填写内容：' + message.map(e => e.loc.slice(1).join('.') + ' ' + e.msg).join('；');
    if (response.status === 401 && !path.startsWith('/auth/login')) window.dispatchEvent(new Event('auth-expired'));
    throw new ApiError(message, response.status);
  }
  return data;
}
export function requestKey() { return (globalThis.crypto?.randomUUID?.() || Date.now() + '-' + Math.random().toString(36).slice(2)); }
export async function downloadSession(id) {
  const r = await fetch('/api/rooms/' + id + '/export', {headers: {Authorization:'Bearer ' + getToken()}});
  if (!r.ok) throw new Error('导出失败，请检查权限');
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = '余烬酒馆-事件档案-' + id.slice(0, 8) + '.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
