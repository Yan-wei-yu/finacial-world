/** Tiny DOM builders. Text always goes through textContent / text nodes — never innerHTML. */
import { safeHttpUrl } from './data.js';

const SVG_NS = 'http://www.w3.org/2000/svg';

function appendChildren(element, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    element.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return element;
}

function applyProps(element, props) {
  for (const [key, value] of Object.entries(props ?? {})) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') element.setAttribute('class', value);
    else if (key === 'text') element.textContent = String(value);
    else if (key === 'dataset') Object.assign(element.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(element.style, value);
    else if (key.startsWith('on') && typeof value === 'function') element.addEventListener(key.slice(2), value);
    else element.setAttribute(key, value === true ? '' : String(value));
  }
  return element;
}

/** @param {string} tag @param {Record<string, any>} [props] @param {...any} children @returns {HTMLElement} */
export function h(tag, props = {}, ...children) {
  return appendChildren(applyProps(document.createElement(tag), props), children);
}

/** @param {string} tag @param {Record<string, any>} [props] @param {...any} children @returns {SVGElement} */
export function s(tag, props = {}, ...children) {
  return appendChildren(applyProps(document.createElementNS(SVG_NS, tag), props), children);
}

/** External link (new tab, no referrer leakage) or plain text when the URL is unsafe. */
export function link(url, props = {}, ...children) {
  const safe = safeHttpUrl(url);
  if (!safe) return h('span', { class: props.class }, ...children);
  return h('a', { ...props, href: safe, target: '_blank', rel: 'noopener noreferrer' }, ...children);
}

/** @param {Element|null} container @param {...any} nodes */
export function mount(container, ...nodes) {
  if (!container) return;
  container.replaceChildren(...nodes.flat(Infinity).filter((n) => n !== null && n !== undefined && n !== false));
}

/** @param {string} id @returns {HTMLElement|null} */
export const byId = (id) => document.getElementById(id);

/** Re-render without losing keyboard focus: controls carry a stable data-key. */
export function preserveFocus(render) {
  const active = document.activeElement;
  const key = active && active !== document.body ? active.getAttribute('data-key') : null;
  render();
  if (key && typeof CSS !== 'undefined') document.querySelector(`[data-key="${CSS.escape(key)}"]`)?.focus({ preventScroll: true });
}
