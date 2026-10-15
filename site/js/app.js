/** Entry point: load the snapshots, render every section, keep clocks ticking and data fresh. */
import { loadAll, mergeSnapshots } from './data.js';
import { byId, preserveFocus } from './dom.js';
import { renderEarnings, renderIndicators, renderMacro } from './render-calendar.js';
import { renderClock, renderFreshness } from './render-header.js';
import { renderMarket } from './render-market.js';
import { renderNews } from './render-news.js';
import { renderPortfolio } from './render-portfolio.js';
import { openSettings } from './render-settings.js';
import { renderSummary } from './render-summary.js';
import { applySettings, effectiveTheme, loadSettings, previousVisit, rememberVisit } from './settings.js';
import { mountCharts, mountTape } from './tradingview.js';

const REFRESH_MS = 5 * 60 * 1000;
const VISIT_SAVE_DELAY_MS = 30 * 1000;

const state = {
  data: null,
  settings: loadSettings(),
  previousVisit: previousVisit(),
  widgetTheme: null,
};

function safely(section, render) {
  try {
    render();
  } catch (error) {
    showError(new Error(`${section}：${error instanceof Error ? error.message : String(error)}`));
  }
}

function renderData(now) {
  const { data, settings } = state;
  if (!data) return;
  const holdingSymbols = new Set(data.quotes.holdings.map((holding) => holding.symbol));
  preserveFocus(() => {
    safely('更新時間', () => renderFreshness(data, now));
    safely('市場指標', () => renderMarket(data.quotes));
    safely('持股', () => renderPortfolio(data, settings));
    safely('AI 摘要', () => renderSummary(data.summary, now));
    safely('新聞', () => renderNews(data.news, data.quotes.holdings, { previousVisit: state.previousVisit, now }));
    safely('財報', () => renderEarnings(data.earnings, now));
    safely('總經', () => renderMacro(data.macro, now, holdingSymbols));
    safely('指標', () => renderIndicators(data.quotes));
  });
}

function updateTapeLabel() {
  const label = byId('tape-label');
  if (!label) return;
  const note = state.settings.updown === 'tw' ? '；TradingView 固定為綠漲紅跌' : '';
  label.textContent = `即時報價・TradingView（指數以 ETF／差價合約代替${note}）`;
}

function renderWidgets(force = false) {
  updateTapeLabel();
  const theme = effectiveTheme(state.settings);
  if (!state.data || (!force && theme === state.widgetTheme)) return;
  state.widgetTheme = theme;
  const tradingview = Array.isArray(state.data.quotes.tradingview) ? state.data.quotes.tradingview : [];
  mountTape(state.data.quotes.holdings, tradingview, theme);
  mountCharts(state.data.quotes.holdings, tradingview, theme);
}

function showError(error) {
  const banner = byId('app-error');
  if (!banner) return;
  banner.hidden = false;
  banner.textContent = `畫面更新失敗：${error instanceof Error ? error.message : String(error)}（稍後會自動重試）`;
}

async function refresh() {
  try {
    const fetched = await loadAll('data/');
    const firstLoad = state.data === null;
    state.data = mergeSnapshots(state.data, fetched);
    const banner = byId('app-error');
    if (banner) banner.hidden = true;
    renderData(new Date());
    renderWidgets(firstLoad);
  } catch (error) {
    showError(error);
  }
}

function wireSettings() {
  const button = byId('settings-open');
  const dialog = byId('settings');
  if (!button || !(dialog instanceof HTMLDialogElement)) return;
  button.addEventListener('click', () => {
    openSettings(dialog, state.data?.quotes.holdings ?? [], state.settings, (next) => {
      state.settings = next;
      renderData(new Date());
      renderWidgets();
    });
  });
}

function start() {
  applySettings(state.settings);
  renderClock(new Date());
  window.setInterval(() => renderClock(new Date()), 1000);
  wireSettings();
  refresh();
  window.setInterval(refresh, REFRESH_MS);
  window.setTimeout(() => rememberVisit(), VISIT_SAVE_DELAY_MS);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') refresh();
  });
  window.matchMedia?.('(prefers-color-scheme: dark)').addEventListener?.('change', () => renderWidgets());
}

start();
