export const TOKEN_KEY = 'ember-session';
export function getToken() { return sessionStorage.getItem(TOKEN_KEY) || ''; }
export function setToken(token) { token ? sessionStorage.setItem(TOKEN_KEY, token) : sessionStorage.removeItem(TOKEN_KEY); }
// Keep app credentials separate from a reverse proxy's Authorization channel.
export function authHeaders() { const token = getToken(); return token ? {'X-Ember-Session': token} : {}; }
export class ApiError extends Error { constructor(message, status) { super(message); this.status = status; } }
export async function api(path, options = {}) {
  const response = await fetch('/api' + path, {
    ...options,
    headers: {'Content-Type': 'application/json', ...authHeaders(), ...options.headers},
    ...(options.body !== undefined ? {body: JSON.stringify(options.body)} : {})
  });
  let data;
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) {
    let message = data.detail || '请求失败，请重试';
    if (Array.isArray(message)) message = '请检查填写内容：' + message.map(e => e.loc.slice(1).join('.') + ' ' + e.msg).join('；');
    if (message && typeof message === 'object') message = (message.message || '创作文件校验失败') + (message.errors?.length ? '：' + message.errors.map(e => e.path + ' ' + e.message).join('；') : '');
    if (response.status === 401 && !path.startsWith('/auth/login')) window.dispatchEvent(new Event('auth-expired'));
    throw new ApiError(message, response.status);
  }
  return data;
}
export function requestKey() { return (globalThis.crypto?.randomUUID?.() || Date.now() + '-' + Math.random().toString(36).slice(2)); }
export async function downloadSession(id) {
  const r = await fetch('/api/rooms/' + id + '/export', {headers: authHeaders()});
  if (!r.ok) throw new Error('导出失败，请检查权限');
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = '余烬酒馆-事件档案-' + id.slice(0, 8) + '.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadJSON(value, filename) {
  const blob = new Blob([JSON.stringify(value, null, 2) + '\n'], {type: 'application/json'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadFile(path, filename) {
  const response = await fetch('/api' + path, {headers: authHeaders()});
  if (!response.ok) throw new Error('导出失败，请检查房主权限或登录状态');
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url; link.download = filename; link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
