/** News feed with category / holding / language filters. Filter state lives in the URL. */
import { byId, h, link, mount, preserveFocus } from './dom.js';
import { fmtDateTime, fmtTime, relativeTime, taipeiDateKey } from './format.js';
import { spanLabel, validFilter } from './news-utils.js';

const PAGE_SIZE = 30;
const TOP_SCORE = 8;
const HALF_LIFE_HOURS = 18;
const CATEGORY_ORDER = ['holdings', 'semis', 'macro', 'world', 'market'];
const KNOWN_CATEGORIES = new Set(CATEGORY_ORDER); // also guards the CSS variable names built from data
const LANGS = [
  ['all', '全部'],
  ['zh', '中文'],
  ['en', '英文'],
];
const SORTS = [
  ['latest', '最新'],
  ['important', '重要'],
];

let view = readViewFromUrl();

function readViewFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return {
    filter: params.get('news') ?? 'all',
    lang: ['zh', 'en'].includes(params.get('lang')) ? params.get('lang') : 'all',
    sort: params.get('sort') === 'important' ? 'important' : 'latest',
    limit: PAGE_SIZE,
  };
}

function writeViewToUrl(next) {
  const params = new URLSearchParams(window.location.search);
  const set = (key, value, fallback) => (value === fallback ? params.delete(key) : params.set(key, value));
  set('news', next.filter, 'all');
  set('lang', next.lang, 'all');
  set('sort', next.sort, 'latest');
  const query = params.toString();
  window.history.replaceState(null, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
}

function matches(item, filter) {
  if (filter === 'all') return true;
  if (filter.startsWith('sym:')) return item.symbols.includes(filter.slice(4));
  return item.categories.includes(filter);
}

function importance(item, nowMs) {
  const ageHours = Math.max(0, (nowMs - Date.parse(item.published)) / 3_600_000);
  return (item.score ?? 0) * 0.5 ** (ageHours / HALF_LIFE_HOURS);
}

function visibleItems(items, current, nowMs) {
  const filtered = items.filter((item) => matches(item, current.filter) && (current.lang === 'all' || item.lang === current.lang));
  if (current.sort === 'important') return [...filtered].sort((a, b) => importance(b, nowMs) - importance(a, nowMs));
  return [...filtered].sort((a, b) => b.published.localeCompare(a.published));
}

function chip(label, value, count, current, onSelect, swatch) {
  return h(
    'button',
    { class: 'chip', type: 'button', 'data-key': `news:${value}`, 'aria-pressed': String(current.filter === value), onclick: () => onSelect({ filter: value }) },
    swatch ? h('span', { class: 'dot', style: { background: swatch }, 'aria-hidden': 'true' }) : null,
    label,
    h('span', { class: 'chip__count', text: String(count) }),
  );
}

function segmented(label, options, selected, key, onSelect) {
  return h(
    'div',
    { class: 'segmented', role: 'group', 'aria-label': label },
    options.map(([value, text]) => h('button', { type: 'button', 'data-key': `news-${key}:${value}`, 'aria-pressed': String(selected === value), onclick: () => onSelect({ [key]: value }), text })),
  );
}

function toolbar(doc, holdings, current, onSelect) {
  const count = (filter) => doc.items.filter((item) => matches(item, filter)).length;
  const categoryChips = CATEGORY_ORDER.filter((key) => typeof doc.categories[key] === 'string').map((key) =>
    chip(doc.categories[key], key, count(key), current, onSelect, `var(--cat-${key})`),
  );
  const symbolChips = holdings.map((holding) => chip(holding.symbol, `sym:${holding.symbol}`, count(`sym:${holding.symbol}`), current, onSelect));
  return h(
    'div',
    { class: 'toolbar' },
    h('div', { class: 'chips', role: 'group', 'aria-label': '新聞分類' }, chip('全部', 'all', doc.items.length, current, onSelect), categoryChips),
    h('div', { class: 'chips', role: 'group', 'aria-label': '依持股篩選' }, symbolChips),
    segmented('語言', LANGS, current.lang, 'lang', onSelect),
    segmented('排序', SORTS, current.sort, 'sort', onSelect),
  );
}

function timeCell(item, todayKey) {
  const sameDay = taipeiDateKey(new Date(item.published)) === todayKey;
  const day = fmtDateTime(item.published).slice(0, 5);
  return h('time', { class: 'news-item__time', datetime: item.published, title: fmtDateTime(item.published) }, fmtTime(item.published), sameDay ? null : h('br'), sameDay ? null : day);
}

function meta(item, labels, isNew, now) {
  const sources = item.also.map((a) => a.source).join('、');
  return h(
    'div',
    { class: 'news-item__meta' },
    isNew ? h('span', { class: 'badge badge--accent', text: '新' }) : null,
    h('span', { text: item.source }),
    h('span', { text: relativeTime(item.published, now) }),
    item.symbols.map((symbol) => h('span', { class: 'badge mono', text: symbol })),
    item.categories
      .filter((key) => key !== 'holdings' && KNOWN_CATEGORIES.has(key))
      .map((key) => h('span', { class: 'tag' }, h('span', { class: 'dot', style: { background: `var(--cat-${key})` }, 'aria-hidden': 'true' }), labels[key] ?? key)),
    item.coverage > 1 ? h('span', { title: `也見於：${sources}`, text: `+${item.coverage - 1} 家媒體報導` }) : null,
  );
}

function newsItem(item, labels, previousVisit, now, todayKey) {
  const isNew = previousVisit !== null && Date.parse(item.first_seen ?? item.published) > previousVisit;
  return h(
    'li',
    { class: `news-item${item.score >= TOP_SCORE ? ' news-item--top' : ''}` },
    timeCell(item, todayKey),
    h(
      'div',
      {},
      link(item.url, { class: 'news-item__title' }, item.title),
      item.summary ? h('p', { class: 'news-item__summary', text: item.summary }) : null,
      meta(item, labels, isNew, now),
    ),
  );
}

/**
 * @param {{items:any[], categories:Record<string,string>}} doc
 * @param {Array<{symbol:string}>} holdings
 * @param {{previousVisit:number|null, now:Date}} context
 */
export function renderNews(doc, holdings, context) {
  const update = (patch) => {
    view = { ...view, ...patch, limit: patch.limit ?? PAGE_SIZE };
    writeViewToUrl(view);
    preserveFocus(() => renderNews(doc, holdings, context));
  };
  const symbols = holdings.map((holding) => holding.symbol);
  const filter = validFilter(view.filter, doc.categories, symbols);
  if (filter !== view.filter) view = { ...view, filter };
  const items = visibleItems(doc.items, view, context.now.getTime());
  const todayKey = taipeiDateKey(context.now);
  const shown = items.slice(0, view.limit);
  mount(
    byId('news-body'),
    toolbar(doc, holdings, view, update),
    shown.length
      ? h('ol', { class: 'news-list' }, shown.map((item) => newsItem(item, doc.categories, context.previousVisit, context.now, todayKey)))
      : h('p', { class: 'empty', text: doc.items.length ? '這個篩選條件下沒有新聞。' : '還沒有新聞資料，等待下一次排程更新。' }),
    items.length > shown.length
      ? h('button', { class: 'more', type: 'button', 'data-key': 'news:more', onclick: () => update({ limit: view.limit + PAGE_SIZE }), text: `顯示更多（還有 ${items.length - shown.length} 則）` })
      : null,
  );
  const fresh = doc.items.filter((item) => context.previousVisit !== null && Date.parse(item.first_seen ?? item.published) > context.previousVisit).length;
  const span = spanLabel(doc.items, context.now);
  mount(byId('news-meta'), `${doc.items.length} 則${span ? `・${span}` : ''}`, fresh ? `・上次造訪後新增 ${fresh} 則` : '');
}
