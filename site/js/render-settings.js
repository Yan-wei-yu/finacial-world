/** Settings dialog: theme, red/green convention and per-browser cost basis. */
import { byId, h, mount } from './dom.js';
import { applySettings, clearSettings, mergeCosts, saveSettings } from './settings.js';

const THEME_OPTIONS = [
  ['auto', '跟隨系統'],
  ['dark', '深色（夜盤）'],
  ['light', '淺色（晨報）'],
];
const UPDOWN_OPTIONS = [
  ['tw', '紅漲綠跌（台灣習慣）'],
  ['us', '綠漲紅跌（美股習慣）'],
];

function select(id, options, value) {
  return h('select', { id }, options.map(([optionValue, label]) => h('option', { value: optionValue, selected: optionValue === value, text: label })));
}

function readForm(holdings, settings) {
  const entries = holdings
    .filter((holding) => byId(`cost-${holding.symbol}`))
    .map((holding) => ({ symbol: holding.symbol, raw: byId(`cost-${holding.symbol}`).value }));
  const { costs, invalid } = mergeCosts(settings.costs, entries);
  return { theme: byId('set-theme').value, updown: byId('set-updown').value, costs, invalid };
}

/**
 * @param {HTMLDialogElement} dialog
 * @param {Array<{symbol:string, name_zh:string}>} holdings
 * @param {object} settings
 * @param {(next:object) => void} onChange
 */
export function openSettings(dialog, holdings, settings, onChange) {
  const error = h('p', { class: 'field__error', role: 'alert' });
  const finish = (next) => {
    applySettings(next);
    onChange(next);
    dialog.close();
  };
  mount(
    dialog,
    h(
      'div',
      { class: 'settings__body' },
      h('h2', { class: 'panel__title', text: '設定' }),
      h('label', { class: 'field' }, '主題', select('set-theme', THEME_OPTIONS, settings.theme)),
      h('label', { class: 'field' }, '漲跌顏色', select('set-updown', UPDOWN_OPTIONS, settings.updown)),
      h(
        'fieldset',
        { class: 'field', style: { border: '0', padding: '0', margin: '0' } },
        h('legend', { text: '成本價（美元／股，選填）' }),
        h(
          'div',
          { class: 'cost-grid' },
          holdings.map((holding) => [
            h('label', { class: 'mono', for: `cost-${holding.symbol}`, text: holding.symbol }),
            h('input', { id: `cost-${holding.symbol}`, type: 'text', inputmode: 'decimal', autocomplete: 'off', placeholder: holding.name_zh, value: settings.costs[holding.symbol] ?? '' }),
          ]),
        ),
        h('p', { class: 'note', text: '成本價只存在這台裝置的瀏覽器，不會上傳到 GitHub。' }),
      ),
      error,
    ),
    h(
      'div',
      { class: 'settings__actions' },
      h('button', { class: 'icon-button', type: 'button', onclick: () => finish(clearSettings()), text: '清除本機設定' }),
      h(
        'div',
        { style: { display: 'flex', gap: '8px' } },
        h('button', { class: 'icon-button', type: 'button', onclick: () => dialog.close(), text: '取消' }),
        h(
          'button',
          {
            class: 'button-primary',
            type: 'button',
            onclick: () => {
              const { invalid, ...next } = readForm(holdings, settings);
              if (invalid.length) {
                error.textContent = `成本價格式不正確：${invalid.join('、')}（請輸入大於 0 的數字）`;
                return;
              }
              finish(saveSettings(next));
            },
            text: '儲存',
          },
        ),
      ),
    ),
  );
  dialog.showModal();
}
