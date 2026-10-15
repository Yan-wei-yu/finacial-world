/** Masthead: Taipei / New York clocks, US session pill with countdown, data freshness. */
import { byId, h, mount } from './dom.js';
import { fmtCountdown, fmtDateTime, relativeTime, TZ_NEW_YORK, TZ_TAIPEI, zonedParts } from './format.js';
import { sessionAt } from './market-clock.js';

// Scheduled news runs (Taipei time) — keep in sync with .github/workflows/update.yml.
const NEWS_RUNS = [
  [8, 52],
  [9, 52],
  [20, 52],
  [21, 52],
];

const pad = (value) => String(value).padStart(2, '0');

function clockText(now, timeZone) {
  const p = zonedParts(now, timeZone);
  return `${pad(p.hour)}:${pad(p.minute)}:${pad(p.second)}`;
}

function clock(label, timeZone, now) {
  return h('div', { class: 'clock' }, h('span', { class: 'clock__label', text: label }), h('time', { class: 'clock__time', text: clockText(now, timeZone) }));
}

/** @param {Date} now */
export function renderClock(now) {
  mount(byId('clocks'), clock('台北', TZ_TAIPEI, now), clock('紐約', TZ_NEW_YORK, now));
  const session = sessionAt(now);
  const pill = byId('session');
  if (!pill) return;
  pill.dataset.phase = session.phase;
  mount(
    pill,
    h('span', { class: 'session__dot', 'aria-hidden': 'true' }),
    h('span', { text: session.reason ?? `美股${session.label}` }),
    h('span', { class: 'session__countdown', text: `${session.targetLabel} ${fmtCountdown(session.target.getTime() - now.getTime())}` }),
  );
}

/** @param {Date} now @returns {string} next scheduled news refresh, "HH:MM" Taipei */
export function nextNewsRun(now) {
  const p = zonedParts(now, TZ_TAIPEI);
  const minutes = p.hour * 60 + p.minute;
  const [hour, minute] = NEWS_RUNS.find(([hh, mm]) => hh * 60 + mm > minutes) ?? NEWS_RUNS[0];
  return `${pad(hour)}:${pad(minute)}`;
}

function stamp(label, iso, now) {
  if (!iso) return h('span', {}, `${label} `, h('strong', { text: '尚無資料' }));
  return h('span', { title: fmtDateTime(iso) }, `${label} `, h('strong', { text: fmtDateTime(iso) }), `（${relativeTime(iso, now)}）`);
}

const STAGE_LABELS = { quotes: '報價', news: '新聞', earnings: '財報', macro: '總經', summary: 'AI 摘要' };

function failedStages(meta) {
  const stages = meta?.stages && typeof meta.stages === 'object' ? meta.stages : {};
  return Object.entries(stages).filter(([, stage]) => stage && stage.ok === false);
}

/** @param {{quotes:any, news:any, meta:any, errors:string[]}} data @param {Date} now */
export function renderFreshness(data, now) {
  const failed = failedStages(data.meta);
  mount(
    byId('freshness'),
    stamp('報價快照', data.quotes.generated_at, now),
    stamp('新聞', data.news.generated_at, now),
    h('span', {}, '下次新聞更新 ', h('strong', { text: nextNewsRun(now) })),
    failed.length
      ? h('span', { class: 'fall', title: failed.map(([name, stage]) => `${STAGE_LABELS[name] ?? name}：${stage.message}`).join('\n') }, `上次排程部分來源失敗：${failed.map(([name]) => STAGE_LABELS[name] ?? name).join('、')}（沿用舊資料）`)
      : null,
    data.errors.length ? h('span', { class: 'fall', text: `本次讀取失敗、沿用畫面上的資料：${data.errors.join('；')}` }) : null,
  );
}
