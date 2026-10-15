/** Market pulse: index / rate / FX tiles from the quote snapshot. */
import { delta, sparkline } from './charts.js';
import { byId, h, mount } from './dom.js';
import { fmtPrice, isNum } from './format.js';

function fmtValue(kind, value) {
  if (!isNum(value)) return '—';
  if (kind === 'yield') return `${value.toFixed(2)}%`;
  if (kind === 'fx') return value.toFixed(value >= 100 ? 2 : 3);
  return fmtPrice(value);
}

function tile(entry, quote) {
  const history = (quote?.history ?? []).slice(-30);
  return h(
    'article',
    { class: `tile${quote?.stale ? ' tile--stale' : ''}`, 'aria-label': entry.label, title: quote?.stale ? '本次抓取失敗，沿用上一次的報價' : null },
    h('span', { class: 'tile__label', text: entry.label }),
    h('span', { class: 'tile__short', text: entry.short ?? entry.symbol }),
    h('span', { class: 'tile__value num', text: fmtValue(entry.kind, quote?.price) }),
    quote ? delta(quote.change_pct, { className: 'tile__delta' }) : h('span', { class: 'tile__delta muted', text: '—' }),
    h('div', { class: 'tile__spark' }, sparkline(history, { width: 150, height: 28, label: `${entry.label} 近 30 個交易日走勢` })),
  );
}

/** @param {{market:any[], quotes:Record<string, any>}} quotesDoc */
export function renderMarket(quotesDoc) {
  mount(
    byId('market-pulse'),
    quotesDoc.market.map((entry) => tile(entry, quotesDoc.quotes[entry.symbol])),
  );
}
