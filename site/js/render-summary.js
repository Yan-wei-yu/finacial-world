/** AI market brief written by Claude (summary.json). Shows setup steps when there is none yet. */
import { byId, h, link, mount } from './dom.js';
import { fmtDateTime, relativeTime } from './format.js';

const IMPACT_CLASS = { 利多: 'badge badge--rise', 利空: 'badge badge--fall', 中性: 'badge' };
const MOOD_CLASS = { 偏多: 'badge badge--rise', 偏空: 'badge badge--fall', 中性: 'badge' };

function refs(sources) {
  if (!sources?.length) return null;
  return h(
    'span',
    { class: 'refs' },
    sources.map((source) => link(source.url, { title: `${source.source}：${source.title}`, 'aria-label': `來源 ${source.n}：${source.title}` }, `[${source.n}]`)),
  );
}

function setupHint() {
  return h(
    'div',
    { class: 'empty' },
    h('strong', { text: 'AI 盤前摘要尚未產生' }),
    h(
      'ol',
      {},
      h('li', { text: '用 Claude 訂閱（Pro／Max）：在自己的電腦執行 claude setup-token，取得 token' }),
      h('li', { text: '在 GitHub repo → Settings → Secrets and variables → Actions 新增 CLAUDE_CODE_OAUTH_TOKEN，貼上 token' }),
      h('li', { text: '之後每天 08:52、09:52、20:52、21:52（台灣時間）自動產生；想馬上看到可到 Actions 手動 Run workflow' }),
    ),
  );
}

/** @param {any} summary @param {Date} now */
export function renderSummary(summary, now) {
  if (!summary) {
    mount(byId('brief-meta'), '');
    mount(byId('brief-body'), setupHint());
    return;
  }
  mount(byId('brief-meta'), `${fmtDateTime(summary.generated_at)}（${relativeTime(summary.generated_at, now)}）`);
  mount(
    byId('brief-body'),
    h('p', { class: 'brief__headline', text: summary.headline }),
    h('p', { class: 'brief__mood' }, h('span', { class: MOOD_CLASS[summary.mood] ?? 'badge', text: `那指／費半氣氛：${summary.mood}` }), summary.mood_reason ?? ''),
    h(
      'ol',
      { class: 'points' },
      summary.key_points.map((point) =>
        h(
          'li',
          { class: 'point' },
          h('span', { class: 'point__title' }, point.title, h('span', { class: IMPACT_CLASS[point.impact] ?? 'badge', text: point.impact })),
          h('span', { class: 'point__detail' }, point.detail, ' ', refs(point.sources)),
        ),
      ),
    ),
    summary.holdings.length ? h('h3', { class: 'panel__sub', text: '對我的持股' }) : null,
    summary.holdings.length
      ? h('ul', { class: 'watch' }, summary.holdings.map((note) => h('li', {}, h('span', { class: 'mono', text: note.symbol }), h('span', {}, note.note, ' ', refs(note.sources)))))
      : null,
    summary.watch_next.length ? h('h3', { class: 'panel__sub', text: '接下來注意' }) : null,
    summary.watch_next.length ? h('ul', { class: 'watch' }, summary.watch_next.map((item) => h('li', {}, h('time', { text: item.when }), h('span', { text: item.what })))) : null,
    h('p', { class: 'note', text: `由 ${summary.model} 依 ${summary.news_count} 則新聞整理，可能有誤；僅供參考，不構成投資建議。` }),
  );
}
