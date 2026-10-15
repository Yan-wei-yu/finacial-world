/** Per-browser preferences in localStorage. Every access is guarded: storage may be unavailable. */

const KEY = 'fw.settings.v1';
const VISIT_KEY = 'fw.lastVisit.v1';
const THEMES = new Set(['auto', 'dark', 'light']);
const UPDOWN = new Set(['tw', 'us']);
const MAX_COST = 1_000_000;

export const DEFAULT_SETTINGS = Object.freeze({ theme: 'auto', updown: 'tw', costs: Object.freeze({}) });

function readRaw(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeRaw(key, value) {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
    return true;
  } catch {
    return false;
  }
}

/** @param {unknown} value @returns {number|null} a sane positive cost basis or null */
export function parseCost(value) {
  const number = typeof value === 'number' ? value : Number(String(value ?? '').replace(/,/g, '').trim());
  return Number.isFinite(number) && number > 0 && number < MAX_COST ? number : null;
}

/**
 * Apply the cost boxes that exist in the dialog; symbols without a box keep their saved cost.
 * @param {Record<string, number>} existing @param {Array<{symbol:string, raw:string}>} entries
 */
export function mergeCosts(existing, entries) {
  const costs = { ...(existing ?? {}) };
  const invalid = [];
  for (const { symbol, raw } of entries) {
    const text = String(raw ?? '').trim();
    if (!text) {
      delete costs[symbol];
    } else if (parseCost(text) === null) {
      invalid.push(symbol);
    } else {
      costs[symbol] = parseCost(text);
    }
  }
  return { costs, invalid };
}

function sanitize(raw) {
  const source = raw && typeof raw === 'object' ? raw : {};
  const costs = {};
  for (const [symbol, value] of Object.entries(source.costs ?? {})) {
    const cost = parseCost(value);
    if (/^[A-Z0-9.^=-]{1,15}$/.test(symbol) && cost !== null) costs[symbol] = cost;
  }
  return {
    theme: THEMES.has(source.theme) ? source.theme : DEFAULT_SETTINGS.theme,
    updown: UPDOWN.has(source.updown) ? source.updown : DEFAULT_SETTINGS.updown,
    costs,
  };
}

/** @returns {{theme:string, updown:string, costs:Record<string, number>}} */
export function loadSettings() {
  try {
    return sanitize(JSON.parse(readRaw(KEY) ?? '{}'));
  } catch {
    return sanitize({});
  }
}

/** @param {object} settings @returns {object} the sanitized settings that were saved */
export function saveSettings(settings) {
  const clean = sanitize(settings);
  writeRaw(KEY, JSON.stringify(clean));
  return clean;
}

export function clearSettings() {
  writeRaw(KEY, null);
  return sanitize({});
}

/** Reflect theme and colour convention on <html> so CSS tokens switch. */
export function applySettings(settings) {
  const root = document.documentElement;
  if (settings.theme === 'auto') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', settings.theme);
  root.setAttribute('data-updown', settings.updown);
}

/** The effective colour scheme ('dark' | 'light') for third-party widgets. */
export function effectiveTheme(settings) {
  if (settings.theme !== 'auto') return settings.theme;
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

/** Timestamp of the previous visit (ms), used for "新" badges. */
export function previousVisit() {
  const value = Number(readRaw(VISIT_KEY));
  return Number.isFinite(value) && value > 0 ? value : null;
}

export function rememberVisit(now = Date.now()) {
  writeRaw(VISIT_KEY, String(now));
}
