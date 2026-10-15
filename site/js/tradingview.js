/** TradingView embeds (live tape, interactive chart, economic calendar). Loaded from s3.tradingview.com. */
import { byId, h, mount } from './dom.js';

const EMBED_BASE = 'https://s3.tradingview.com/external-embedding/embed-widget-';
let chartSymbol = null;

function embed(container, widget, config) {
  if (!container) return;
  const script = document.createElement('script');
  script.src = `${EMBED_BASE}${widget}.js`;
  script.async = true;
  // TradingView reads its JSON config from the script element's text; it is never executed as code.
  script.textContent = JSON.stringify(config);
  // The iframe's prefers-color-scheme follows the host element, so keep it aligned with the widget theme.
  const scheme = config.colorTheme ?? config.theme ?? 'light';
  mount(container, h('div', { class: 'tradingview-widget-container', style: { height: '100%', colorScheme: scheme } }, h('div', { class: 'tradingview-widget-container__widget', style: { height: '100%' } }), script));
}

// Free widgets cannot show Nasdaq/CBOE index feeds (IXIC, SOX, VIX), so watchlist.json lists
// widget-safe proxies (ETFs / CFDs) under "tradingview"; exact index values come from the snapshot tiles.
function tapeSymbols(holdings, tradingview) {
  const fromHoldings = holdings.filter((holding) => holding.tv_symbol).map((holding) => ({ proName: holding.tv_symbol, title: holding.symbol }));
  const extras = tradingview.filter((entry) => entry.tape).map((entry) => ({ proName: entry.tv_symbol, title: entry.label }));
  return [...fromHoldings, ...extras];
}

/** Live ticker tape under the masthead. */
export function mountTape(holdings, tradingview, theme) {
  embed(byId('tape-widget'), 'ticker-tape', {
    symbols: tapeSymbols(holdings, tradingview),
    showSymbolLogo: false,
    isTransparent: false,
    displayMode: 'compact',
    colorTheme: theme,
    locale: 'zh_TW',
  });
}

function mountChart(symbol, theme) {
  chartSymbol = symbol;
  embed(byId('chart-widget'), 'advanced-chart', {
    autosize: true,
    symbol,
    interval: 'D',
    timezone: 'Asia/Taipei',
    theme,
    style: '1',
    locale: 'zh_TW',
    allow_symbol_change: true,
    hide_side_toolbar: true,
    calendar: false,
    support_host: 'https://www.tradingview.com',
  });
}

/** Symbol tabs + advanced chart + economic calendar. */
export function mountCharts(holdings, tradingview, theme) {
  const choices = [
    ...holdings.filter((holding) => holding.tv_symbol).map((holding) => [holding.tv_symbol, holding.symbol]),
    ...tradingview.filter((entry) => entry.chart).map((entry) => [entry.tv_symbol, entry.label]),
  ];
  const selected = chartSymbol ?? choices[0]?.[0];
  if (!selected) return;
  const renderTabs = (active) =>
    mount(
      byId('chart-tabs'),
      choices.map(([symbol, label]) =>
        h('button', {
          class: 'chip',
          type: 'button',
          'data-key': `chart:${symbol}`,
          'aria-pressed': String(symbol === active),
          onclick: () => {
            renderTabs(symbol);
            mountChart(symbol, theme);
          },
          text: label,
        }),
      ),
    );
  renderTabs(selected);
  mountChart(selected, theme);
  embed(byId('calendar-widget'), 'events', {
    colorTheme: theme,
    isTransparent: false,
    width: '100%',
    height: '100%',
    locale: 'zh_TW',
    importanceFilter: '0,1',
    countryFilter: 'us,tw,kr,cn,jp',
  });
}
