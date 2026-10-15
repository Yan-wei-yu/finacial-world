/** Portfolio hero (total value, day P/L, allocation) and the holdings table. */
import { allocationBar, delta, sparkline } from './charts.js';
import { byId, h, mount, preserveFocus } from './dom.js';
import { direction, fmtDate, fmtMoney, fmtPct, fmtPrice, fmtShares, isNum, taipeiDateKey } from './format.js';
import { buildPositions, summarize } from './portfolio.js';

const SPARK_LABEL = '近 3 月';
const expanded = new Set();

function signedMoney(value, digits = 2) {
  if (!isNum(value)) return '—';
  return `${value > 0 ? '+' : ''}${fmtMoney(value, 'USD', digits)}`;
}

function stat(label, value, sub, tone) {
  return h(
    'div',
    { class: 'stat' },
    h('dt', { class: 'stat__label', text: label }),
    h('dd', { class: `stat__value num ${tone ?? ''}`.trim() }, value, sub ? h('small', { text: sub }) : null),
  );
}

function heroStats(summary, positions) {
  const extLabel = positions.find((p) => p.extLabel)?.extLabel;
  return h(
    'dl',
    { class: 'stat-list' },
    stat('今日損益', signedMoney(summary.dayChange), fmtPct(summary.dayChangePct), direction(summary.dayChange)),
    summary.extTotal !== null
      ? stat(`${extLabel ?? '盤外'}估算`, signedMoney(summary.extChange), `以${extLabel ?? '盤外'}價計 ${fmtPct(summary.extChangePct)}`, direction(summary.extChange))
      : null,
    summary.pnl !== null
      ? stat('未實現損益', signedMoney(summary.pnl), `成本 ${fmtMoney(summary.costBasis, 'USD')}・${fmtPct(summary.pnlPct)}`, direction(summary.pnl))
      : stat('未實現損益', '—', '在「設定」輸入成本價即可計算', 'muted'),
  );
}

function renderHero(quotesDoc, positions, summary) {
  const rate = quotesDoc.fx?.USDTWD;
  const staleCount = positions.filter((p) => p.stale).length;
  mount(
    byId('portfolio-body'),
    h(
      'div',
      { class: 'hero' },
      h(
        'div',
        {},
        h('p', { class: 'hero__label', text: `持股總市值（${summary.pricedCount}/${summary.count} 檔有報價）` }),
        h('p', { class: 'hero__value' }, h('span', { class: 'hero__currency', text: 'US$' }), summary.total.toLocaleString('en-US', { maximumFractionDigits: 0 })),
        h('p', { class: 'hero__twd', text: isNum(rate) ? `約 ${fmtMoney(summary.total * rate, 'TWD')}（USD/TWD ${rate.toFixed(3)}）` : '' }),
      ),
      heroStats(summary, positions),
    ),
    allocationBar(summary.weights),
    staleCount ? h('p', { class: 'note', text: `有 ${staleCount} 檔報價沿用上一次的資料（本次抓取失敗）。` }) : null,
  );
}

function rangeBar(quote) {
  const { low_52w: low, high_52w: high, price } = quote ?? {};
  if (![low, high, price].every(isNum) || high <= low) return h('p', { class: 'muted', text: '—' });
  const position = Math.min(100, Math.max(0, ((price - low) / (high - low)) * 100));
  return h(
    'div',
    {},
    h('div', { class: 'range', role: 'img', 'aria-label': `52 週區間 ${fmtPrice(low)} 至 ${fmtPrice(high)}，目前在 ${position.toFixed(0)}%` }, h('span', { class: 'range__marker', style: { left: `${position}%` } })),
    h('div', { class: 'range__labels num' }, h('span', { text: fmtPrice(low) }), h('span', { text: fmtPrice(high) })),
  );
}

function earningsLine(symbol, earnings) {
  const next = earnings?.upcoming?.find((e) => e.symbol === symbol);
  const history = earnings?.history?.[symbol] ?? [];
  return h(
    'div',
    {},
    h('h4', { text: '財報（法說會）' }),
    next
      ? h('p', {}, `下次：${fmtDate(next.datetime ? taipeiDateKey(new Date(next.datetime)) : next.date)}（台灣）${next.session}`, h('br'), `EPS 預估 ${isNum(next.eps_est) ? next.eps_est.toFixed(3) : '—'}`)
      : h('p', { class: 'muted', text: '尚未公布日期' }),
    history.length
      ? h(
          'ul',
          {},
          history.map((row) =>
            h('li', {}, `${fmtDate(row.date)}：EPS ${isNum(row.eps_actual) ? row.eps_actual.toFixed(3) : '—'}（預估 ${isNum(row.eps_est) ? row.eps_est.toFixed(3) : '—'}）`, ' ', isNum(row.surprise_pct) ? delta(row.surprise_pct, { digits: 1 }) : h('span', { class: 'muted', text: row.suspect ? '資料異常' : '' })),
          ),
        )
      : null,
  );
}

function detailsRow(position, earnings, id) {
  return h(
    'tr',
    { class: 'details-row', id },
    h(
      'td',
      { colspan: 9 },
      h(
        'div',
        { class: 'details' },
        h('div', {}, h('h4', { text: '觀察重點' }), h('ul', {}, position.drivers.map((d) => h('li', { text: d })))),
        h('div', {}, h('h4', { text: '52 週區間' }), rangeBar(position.quote), h('p', { class: 'note', text: `${position.exchange}・${position.kind}` })),
        earningsLine(position.symbol, earnings),
      ),
    ),
  );
}

function cell(label, ...children) {
  return h('td', { 'data-label': label, class: label === SPARK_LABEL ? 'col-spark' : null }, ...children);
}

function positionRows(position, weight, earnings, rerender) {
  const id = `details-${position.symbol}`;
  const open = expanded.has(position.symbol);
  const toggle = () => {
    if (expanded.has(position.symbol)) expanded.delete(position.symbol);
    else expanded.add(position.symbol);
    preserveFocus(rerender);
  };
  const row = h(
    'tr',
    { class: 'position', onclick: (event) => event.target.closest('a') || toggle() },
    h(
      'td',
      {},
      h(
        'div',
        { class: 'ticker' },
        h('button', { class: 'icon-button', type: 'button', 'data-key': `holding:${position.symbol}`, 'aria-expanded': String(open), 'aria-controls': id, 'aria-label': `${position.symbol} 詳細資料`, onclick: (event) => { event.stopPropagation(); toggle(); } }, open ? '−' : '+'),
        h('div', {}, h('span', { class: 'ticker__symbol', text: position.symbol }), h('span', { class: 'ticker__name', text: position.name_zh })),
      ),
    ),
    cell('股數', h('span', { class: 'num', text: fmtShares(position.shares) })),
    cell('價格', h('span', { class: 'num', text: fmtPrice(position.price) }), position.stale ? h('span', { class: 'ext muted', text: '舊資料' }) : null),
    cell('今日', delta(position.dayChangePct), h('span', { class: `ext num ${direction(position.dayChange)}`, text: signedMoney(position.dayChange, 0) })),
    cell('盤前／盤後', position.extPrice !== null ? h('span', {}, h('span', { class: 'num', text: fmtPrice(position.extPrice) }), h('span', { class: 'ext' }, `${position.extLabel} `, delta(position.extChangePct))) : h('span', { class: 'muted', text: '—' })),
    cell('市值', h('span', { class: 'num', text: fmtMoney(position.value, 'USD') })),
    cell('占比', h('span', { class: 'num', text: `${weight.toFixed(1)}%` })),
    cell('損益', position.pnl !== null ? h('span', {}, h('span', { class: `num ${direction(position.pnl)}`, text: signedMoney(position.pnl, 0) }), h('span', { class: 'ext' }, delta(position.pnlPct))) : h('span', { class: 'muted', text: '—' })),
    cell(SPARK_LABEL, sparkline(position.quote?.history, { width: 120, height: 30, label: `${position.symbol} 近 3 個月走勢` })),
  );
  return open ? [row, detailsRow(position, earnings, id)] : [row];
}

function renderTable(positions, summary, earnings, rerender) {
  const headers = ['標的', '股數', '價格', '今日', '盤前／盤後', '市值', '占比', '損益', '近 3 月'];
  mount(
    byId('holdings-body'),
    h(
      'div',
      { class: 'table-wrap' },
      h(
        'table',
        { class: 'holdings' },
        h('caption', { class: 'visually-hidden', text: '持股明細，點選列可展開觀察重點與財報資訊' }),
        h('thead', {}, h('tr', {}, headers.map((label) => h('th', { scope: 'col', class: label === SPARK_LABEL ? 'col-spark' : null, text: label })))),
        h('tbody', {}, positions.map((position, index) => positionRows(position, summary.weights[index].weight, earnings, rerender))),
      ),
    ),
  );
}

/**
 * @param {{quotes:any, earnings:any}} data
 * @param {{costs:Record<string, number>}} settings
 */
export function renderPortfolio(data, settings) {
  const positions = buildPositions(data.quotes.holdings, data.quotes.quotes, settings.costs);
  const summary = summarize(positions);
  renderHero(data.quotes, positions, summary);
  renderTable(positions, summary, data.earnings, () => renderPortfolio(data, settings));
  return { positions, summary };
}
