import {useEffect, useLayoutEffect, useState} from 'react';

export const THEME_TOKENS = ['--bg', '--surface', '--surface-2', '--surface-3', '--border', '--text', '--muted', '--faint', '--gold', '--gold-hover', '--gold-bg', '--green', '--green-bg', '--red', '--red-bg'];
const read = (key, fallback) => {try {return localStorage.getItem(key) || fallback;} catch {return fallback;}};
const store = (key, value) => {try {value ? localStorage.setItem(key, value) : localStorage.removeItem(key);} catch { /* private browsing may disallow storage */ }};

function safeTheme(value) {
  if (value?.format !== 'ember.theme/v1' || typeof value.metadata?.name !== 'string' || !value.modes) return null;
  const palettes = Object.values(value.modes).filter(Boolean);
  if (!palettes.length || !palettes.every(p => THEME_TOKENS.every(k => /^#[0-9a-f]{6}$/i.test(p[k])) && Object.keys(p).every(k => THEME_TOKENS.includes(k)))) return null;
  return value;
}

function savedTheme() {
  try {return safeTheme(JSON.parse(read('ember-custom-theme', 'null')));} catch {return null;}
}

export function useAppearance() {
  const [theme, setTheme] = useState(() => read('ember-theme', 'dark') === 'light' ? 'light' : 'dark');
  const [custom, setCustom] = useState(savedTheme);
  const key = theme + ':' + JSON.stringify(custom?.modes || {});
  useLayoutEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = theme;
    THEME_TOKENS.forEach(token => root.style.removeProperty(token));
    const palette = custom?.modes[theme];
    if (palette) THEME_TOKENS.forEach(token => root.style.setProperty(token, palette[token]));
  }, [theme, custom]);
  useEffect(() => {store('ember-theme', theme);}, [theme]);
  useEffect(() => {store('ember-custom-theme', custom ? JSON.stringify(custom) : '');}, [custom]);
  function install(value) {
    const parsed = safeTheme(value);
    if (!parsed) throw new Error('主题包含不支持的设计令牌');
    setCustom(parsed);
    if (!parsed.modes[theme]) setTheme(parsed.modes.dark ? 'dark' : 'light');
  }
  return {theme, custom, key, install, reset: () => setCustom(null), toggleTheme: () => setTheme(t => t === 'dark' ? 'light' : 'dark')};
}
