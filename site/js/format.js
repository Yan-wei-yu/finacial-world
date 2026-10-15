/** Formatting helpers. Pure functions, no DOM access (unit-tested in Node). */

export const TZ_TAIPEI = 'Asia/Taipei';
export const TZ_NEW_YORK = 'America/New_York';

const MINUS = '−';
const DASH = '—';
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六'];
const WEEKDAY_INDEX = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
const CURRENCY_PREFIX = { USD: 'US$', TWD: 'NT$' };
const CURRENCY_ZH = { USD: '美元', EUR: '歐元', KRW: '韓元', TWD: '台幣', SEK: '瑞典克朗', JPY: '日圓' };
const UNITS = [
  [1e12, '兆'],
  [1e8, '億'],
  [1e4, '萬'],
];
const formatters = new Map();

/** @param {unknown} value @returns {value is number} */
export const isNum = (value) => typeof value === 'number' && Number.isFinite(value);

const pad = (value) => String(value).padStart(2, '0');
const grouped = (value, min, max) => value.toLocaleString('en-US', { minimumFractionDigits: min, maximumFractionDigits: max });
const withMinus = (text) => text.replace('-', MINUS);
const trim2 = (value) => String(Number(value.toFixed(2)));

/** @param {unknown} value @returns {string} price with magnitude-aware decimals */
export function fmtPrice(value) {
  if (!isNum(value)) return DASH;
  const abs = Math.abs(value);
  if (abs >= 100000) return withMinus(grouped(value, 0, 0));
  if (abs >= 1) return withMinus(grouped(value, 2, 2));
  return withMinus(grouped(value, 4, 4));
}

/** @param {unknown} value @param {number} [digits] @returns {string} e.g. "+1.23" */
export function fmtSigned(value, digits = 2) {
  if (!isNum(value)) return DASH;
  const rounded = Number(value.toFixed(digits));
  const sign = rounded > 0 ? '+' : rounded < 0 ? MINUS : '';
  return `${sign}${grouped(Math.abs(rounded), digits, digits)}`;
}

/** @param {unknown} value @param {number} [digits] @returns {string} e.g. "−4.57%" */
export function fmtPct(value, digits = 2) {
  return isNum(value) ? `${fmtSigned(value, digits)}%` : DASH;
}

/** @param {unknown} value @param {string} [currency] @param {number} [digits] */
export function fmtMoney(value, currency = 'USD', digits = 0) {
  if (!isNum(value)) return DASH;
  const prefix = CURRENCY_PREFIX[currency] ?? `${currency} `;
  return `${value < 0 ? MINUS : ''}${prefix}${grouped(Math.abs(value), digits, digits)}`;
}

/** @param {unknown} value @returns {string} share count, fractional shares allowed */
export function fmtShares(value) {
  return isNum(value) ? grouped(value, 0, 4) : DASH;
}

/** @param {unknown} value @returns {string} 萬 / 億 / 兆 compact form */
export function fmtCompactZh(value) {
  if (!isNum(value)) return DASH;
  const sign = value < 0 ? MINUS : '';
  const abs = Math.abs(value);
  for (const [size, unit] of UNITS) {
    if (abs >= size) return `${sign}${trim2(abs / size)} ${unit}`;
  }
  return `${sign}${trim2(abs)}`;
}

/** @param {unknown} value @param {string} currency @returns {string} e.g. "50.67 億歐元" */
export function fmtRevenue(value, currency) {
  if (!isNum(value)) return DASH;
  const name = CURRENCY_ZH[currency];
  return name ? `${fmtCompactZh(value)}${name}` : `${fmtCompactZh(value)} ${currency}`;
}

/** @param {unknown} value @returns {'rise'|'fall'|'flat'} */
export function direction(value) {
  if (!isNum(value) || value === 0) return 'flat';
  return value > 0 ? 'rise' : 'fall';
}

function formatterFor(timeZone) {
  if (!formatters.has(timeZone)) {
    formatters.set(
      timeZone,
      new Intl.DateTimeFormat('en-US', {
        timeZone,
        hourCycle: 'h23',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        weekday: 'short',
      }),
    );
  }
  return formatters.get(timeZone);
}

/**
 * Wall-clock parts of an instant in a time zone.
 * @param {Date} date @param {string} [timeZone]
 * @returns {{year:number, month:number, day:number, hour:number, minute:number, second:number, weekday:number}}
 */
export function zonedParts(date, timeZone = TZ_TAIPEI) {
  const parts = Object.fromEntries(formatterFor(timeZone).formatToParts(date).map((p) => [p.type, p.value]));
  return {
    year: Number(parts.year),
    month: Number(parts.month),
    day: Number(parts.day),
    hour: Number(parts.hour) % 24,
    minute: Number(parts.minute),
    second: Number(parts.second),
    weekday: WEEKDAY_INDEX[parts.weekday],
  };
}

const toDate = (iso) => {
  if (typeof iso !== 'string') return null;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? null : date;
};

/** @param {string} iso @param {string} [timeZone] @returns {string} "HH:MM" */
export function fmtTime(iso, timeZone = TZ_TAIPEI) {
  const date = toDate(iso);
  if (!date) return DASH;
  const p = zonedParts(date, timeZone);
  return `${pad(p.hour)}:${pad(p.minute)}`;
}

/** @param {string} iso @param {string} [timeZone] @returns {string} "MM/DD (週) HH:MM" */
export function fmtDateTime(iso, timeZone = TZ_TAIPEI) {
  const date = toDate(iso);
  if (!date) return DASH;
  const p = zonedParts(date, timeZone);
  return `${pad(p.month)}/${pad(p.day)} (${WEEKDAYS[p.weekday]}) ${pad(p.hour)}:${pad(p.minute)}`;
}

/** @param {string} dateKey "YYYY-MM-DD" (a calendar date, no time zone) */
export function fmtDate(dateKey) {
  if (typeof dateKey !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(dateKey)) return DASH;
  const [year, month, day] = dateKey.split('-').map(Number);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return `${pad(month)}/${pad(day)} (${WEEKDAYS[weekday]})`;
}

/** @param {Date} date @returns {string} Taipei calendar date "YYYY-MM-DD" */
export function taipeiDateKey(date) {
  const p = zonedParts(date, TZ_TAIPEI);
  return `${p.year}-${pad(p.month)}-${pad(p.day)}`;
}

/** @param {string} dateKey @param {Date} [now] @returns {number} days from today (Taipei) */
export function daysUntil(dateKey, now = new Date()) {
  const toUtc = (key) => {
    const [y, m, d] = key.split('-').map(Number);
    return Date.UTC(y, m - 1, d);
  };
  return Math.round((toUtc(dateKey) - toUtc(taipeiDateKey(now))) / 86_400_000);
}

/** @param {string} iso @param {Date} [now] @returns {string} "5 小時前" */
export function relativeTime(iso, now = new Date()) {
  const date = toDate(iso);
  if (!date) return DASH;
  const seconds = Math.max(0, (now.getTime() - date.getTime()) / 1000);
  if (seconds < 60) return '剛剛';
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分鐘前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小時前`;
  return `${Math.floor(seconds / 86400)} 天前`;
}

/** @param {number} ms @returns {string} "1:02:03" or "1 天 1 小時" */
export function fmtCountdown(ms) {
  const total = Math.max(0, Math.floor((isNum(ms) ? ms : 0) / 1000));
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  if (days >= 1) return `${days} 天 ${hours} 小時`;
  const minutes = Math.floor((total % 3600) / 60);
  return `${hours}:${pad(minutes)}:${pad(total % 60)}`;
}
