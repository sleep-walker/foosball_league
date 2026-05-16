/**
 * Lightweight i18n: locale state, translation lookup, interpolation.
 * Locale is persisted in localStorage; auto-detected from navigator.language.
 */
import en from './locales/en.js';
import cs from './locales/cs.js';

const DICTS = { en, cs };
const SUPPORTED = Object.keys(DICTS);
const STORAGE_KEY = 'locale';

const _listeners = new Set();
let _locale = _initLocale();

function _initLocale() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && SUPPORTED.includes(stored)) return stored;
  const nav = (navigator.language || 'en').toLowerCase();
  for (const code of SUPPORTED) {
    if (nav === code || nav.startsWith(`${code}-`)) return code;
  }
  return 'en';
}

function getLocale() { return _locale; }

function setLocale(code) {
  if (!SUPPORTED.includes(code) || code === _locale) return;
  _locale = code;
  localStorage.setItem(STORAGE_KEY, code);
  document.documentElement.setAttribute('lang', code);
  for (const cb of _listeners) {
    try { cb(code); } catch (_) { /* listener errors are non-fatal */ }
  }
}

function onLocaleChange(cb) {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}

function _lookup(dict, key) {
  if (!dict) return undefined;
  const parts = key.split('.');
  let cur = dict;
  for (const p of parts) {
    if (cur && typeof cur === 'object' && p in cur) cur = cur[p];
    else return undefined;
  }
  return typeof cur === 'string' ? cur : undefined;
}

function _interpolate(str, params) {
  if (!params) return str;
  return str.replace(/\{(\w+)\}/g, (_, k) => (k in params ? String(params[k]) : `{${k}}`));
}

/**
 * Translate a key. Falls back to English, then to the key itself.
 * Supports {param} interpolation.
 */
function t(key, params) {
  const v = _lookup(DICTS[_locale], key) ?? _lookup(DICTS.en, key);
  return _interpolate(v ?? key, params);
}

// Reflect initial locale on <html lang>
document.documentElement.setAttribute('lang', _locale);

export { t, getLocale, setLocale, onLocaleChange, SUPPORTED };
export default { t, getLocale, setLocale, onLocaleChange, SUPPORTED };
