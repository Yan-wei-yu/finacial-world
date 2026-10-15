/** Earnings calendar (法說會), economic calendar and market indicators. */
import { delta, sparkline } from './charts.js';
import { byId, h, mount } from './dom.js';
import { daysUntil, fmtDate, fmtDateTime, fmtPct, fmtRevenue, fmtTime, isNum, taipeiDateKey } from './format.js';

const EARNINGS_DAYS = 45;
const EARNINGS_PREVIEW = 10;
const KEY_DATES_PREVIEW = 8;
const IMPACT_DOTS = { High: '●●●', Medium: '●●○', Low: '●○○' };
const GROUP_LABEL = { holding: '持股', memory: '記憶體', semis: '半導體', capex: 'AI 資本支出', peer: '同業' };

let showAllEarnings = false;

function relativeDay(dateKey, now) {
  const days = daysUntil(dateKey, now);
  if (days === 0) return '今天';
  if (days === 1) return '明天';
  if (days === -1) return '昨天';
  return days > 0 ? `${days} 天後` : `${-days} 天前`;
}

function eventDateKey(event) {
  return event.datetime ? taipeiDateKey(new Date(event.datetime)) : event.date;
}

function groupByDay(events) {
  const groups = new Map();
  for (const event of events) {
    const key = eventDateKey(event);
    groups.set(key, [...(groups.get(key) ?? []), event]);
  }
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
}

function dayBlock(dateKey, rows, now) {
  return h(
    'div',
    { class: 'day' },
    h('div', { class: 'day__head' }, h('strong', { text: fmtDate(dateKey) }), h('span', { text: relativeDay(dateKey, now) })),
    rows,
  );
}

function stackedRow(className, timeText, line, sub) {
  return h(
    'div',
    { class: `event event--stacked ${className}`.trim() },
    h('span', { class: 'event__meta', style: { textAlign: 'left' }, text: timeText }),
    h('div', {}, h('div', { class: 'event__line' }, line), sub ? h('div', { class: 'event__est' }, sub) : null),
  );
}

function earningsRow(event) {
  const estimates = [
    isNum(event.eps_est) ? `EPS 預估 ${event.eps_est.toFixed(2)}` : null,
    isNum(event.rev_est) ? `營收 ${fmtRevenue(event.rev_est, event.rev_currency)}` : null,
  ].filter(Boolean).join('・');
  // Yahoo's release times are placeholders; they are only roughly right for US companies (pre-open / after-close).
  const showTime = event.datetime && event.rev_currency === 'USD' && event.session !== '時間未定';
  return stackedRow(
    event.is_holding ? 'event--holding' : '',
    showTime ? `約${fmtTime(event.datetime)}` : '—',
    [
      h('span', { class: 'event__symbol', text: event.symbol }),
      h('span', { text: event.name_zh }),
      h('span', { class: 'badge', text: event.session }),
      event.is_holding ? h('span', { class: 'badge badge--accent', text: '持股' }) : null,
    ],
    estimates,
  );
}

function recentRow(row) {
  const actual = isNum(row.eps_actual) ? row.eps_actual.toFixed(2) : '—';
  const estimate = isNum(row.eps_est) ? row.eps_est.toFixed(2) : '—';
  return stackedRow(
    row.is_holding ? 'event--holding' : '',
    fmtDate(row.date).slice(0, 5),
    [
      h('span', { class: 'event__symbol', text: row.symbol }),
      h('span', { text: row.name_zh }),
      isNum(row.surprise_pct) ? delta(row.surprise_pct, { digits: 1 }) : h('span', { class: 'muted', text: row.suspect ? '資料異常' : '' }),
    ],
    `EPS ${actual}（預估 ${estimate}）`,
  );
}

/** @param {any} earnings @param {Date} now */
export function renderEarnings(earnings, now) {
  if (!earnings) {
    mount(byId('earnings-body'), h('p', { class: 'empty', text: '財報資料暫時無法取得。' }));
    return;
  }
  const soon = earnings.upcoming.filter((e) => {
    const days = daysUntil(eventDateKey(e), now);
    return days >= 0 && days <= EARNINGS_DAYS;
  });
  const shown = showAllEarnings ? soon : soon.slice(0, EARNINGS_PREVIEW);
  const groups = groupByDay(shown);
  const toggle = () => {
    showAllEarnings = !showAllEarnings;
    renderEarnings(earnings, now);
  };
  mount(
    byId('earnings-body'),
    groups.length
      ? h('div', { class: 'timeline' }, groups.map(([key, rows]) => dayBlock(key, rows.map(earningsRow), now)))
      : h('p', { class: 'empty', text: `未來 ${EARNINGS_DAYS} 天沒有追蹤中的財報。` }),
    soon.length > EARNINGS_PREVIEW
      ? h('button', { class: 'more', type: 'button', 'data-key': 'earnings:more', onclick: toggle, text: showAllEarnings ? '收合' : `顯示全部 ${soon.length} 場（${EARNINGS_DAYS} 天內）` })
      : null,
    earnings.recent.length ? h('h3', { class: 'panel__sub', text: '最近公布（EPS 實際 vs 預估）' }) : null,
    earnings.recent.length ? h('div', { class: 'timeline' }, earnings.recent.slice(0, 5).map(recentRow)) : null,
    h('p', { class: 'note', text: `時間為台灣時間的約略值（美國公司盤前／盤後慣例）；海外公司以當地時間公布，請以公司公告為準。追蹤：${[...new Set(earnings.upcoming.map((e) => GROUP_LABEL[e.group]).filter(Boolean))].join('、')}。資料更新於 ${fmtDateTime(earnings.generated_at)}` }),
  );
}

function macroRow(event, now) {
  const past = Date.parse(event.datetime) < now.getTime();
  const numbers = [event.forecast ? `預期 ${event.forecast}` : null, event.previous ? `前值 ${event.previous}` : null].filter(Boolean).join('・');
  return stackedRow(
    past ? 'event--past' : '',
    fmtTime(event.datetime),
    [
      h('span', { class: 'impact', title: `重要性：${event.impact}`, text: IMPACT_DOTS[event.impact] ?? '' }),
      event.country === 'USD' ? null : h('span', { class: 'badge', text: event.country_label }),
      h('span', { text: event.title_zh ?? event.title }),
    ],
    past ? `已公布・${numbers}` : numbers,
  );
}

function keyDateRow(event, holdingSymbols) {
  const mine = (event.affects ?? []).some((symbol) => holdingSymbols.has(symbol));
  return stackedRow(
    mine ? 'event--holding' : '',
    event.datetime ? fmtTime(event.datetime) : event.approx ? '約' : '',
    [h('span', { text: event.title }), ...(event.affects ?? []).map((symbol) => h('span', { class: 'badge mono', text: symbol }))],
    event.note ?? '',
  );
}

/** @param {any} macro @param {Date} now @param {Set<string>} holdingSymbols */
export function renderMacro(macro, now, holdingSymbols) {
  if (!macro) {
    mount(byId('macro-body'), h('p', { class: 'empty', text: '總經資料暫時無法取得。' }));
    return;
  }
  const week = groupByDay(macro.week.map((e) => ({ ...e, date: taipeiDateKey(new Date(e.datetime)) })));
  const upcoming = groupByDay(macro.upcoming.slice(0, KEY_DATES_PREVIEW));
  mount(
    byId('macro-body'),
    week.length
      ? h('div', { class: 'timeline' }, week.map(([key, rows]) => dayBlock(key, rows.map((e) => macroRow(e, now)), now)))
      : h('p', { class: 'empty', text: '本週經濟數據暫無資料。' }),
    h('h3', { class: 'panel__sub', text: '重要日程（FOMC、記憶體與台積電指標）' }),
    h('div', { class: 'timeline' }, upcoming.map(([key, rows]) => dayBlock(key, rows.map((event) => keyDateRow(event, holdingSymbols)), now))),
    h('p', { class: 'note', text: `資料：ForexFactory（本週）、聯準會與各機構公告。更新於 ${fmtDateTime(macro.generated_at)}` }),
  );
}

/** @param {{indicators:any[]}} quotesDoc */
export function renderIndicators(quotesDoc) {
  const rows = quotesDoc.indicators.map((indicator) =>
    h(
      'div',
      { class: 'indicator' },
      h('div', {}, h('div', { text: indicator.label }), h('div', { class: 'note', text: `${indicator.note}・ADR US$${indicator.adr_price} vs 換算 US$${indicator.implied_price}` })),
      h('div', { class: 'indicator__value num', text: fmtPct(indicator.value, 1) }),
      h('div', { class: 'indicator__spark' }, sparkline(indicator.history, { width: 300, height: 34, label: `${indicator.label} 近 30 日變化` })),
    ),
  );
  mount(
    byId('indicators-body'),
    rows.length ? rows : h('p', { class: 'empty', text: '指標資料暫無。' }),
    h('p', { class: 'note', text: '溢價 = ADR 價格 ÷（本地股價 × 換股比例 ÷ 匯率）− 1，以雙方最近收盤計算。溢價越高，回落風險越大。' }),
  );
}
