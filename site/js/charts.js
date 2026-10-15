/** Small inline SVG charts: sparklines and the allocation bar. */
import { h, s } from './dom.js';
import { direction, fmtPct, isNum } from './format.js';

const SERIES = ['var(--series-1)', 'var(--series-2)', 'var(--series-3)', 'var(--series-4)'];

/**
 * Sparkline in a de-emphasised ink with the latest point marked by direction.
 * @param {Array<{d:string, c:number}>} points
 * @param {{width?:number, height?:number, label?:string, trend?:number|null}} [options]
 */
export function sparkline(points, { width = 132, height = 32, label = '', trend = null } = {}) {
  const values = (points ?? []).map((p) => p?.c).filter(isNum);
  if (values.length < 2) return h('span', { class: 'muted', text: '—' });
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pad = 4;
  const x = (i) => pad + (i / (values.length - 1)) * (width - pad * 2);
  const y = (v) => pad + (1 - (v - min) / span) * (height - pad * 2);
  const path = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('');
  const area = `${path}L${x(values.length - 1).toFixed(1)},${height}L${x(0).toFixed(1)},${height}Z`;
  const last = values[values.length - 1];
  const tone = direction(isNum(trend) ? trend : last - values[0]);
  const color = tone === 'flat' ? 'var(--ink-3)' : `var(--${tone})`;
  return s(
    'svg',
    { viewBox: `0 0 ${width} ${height}`, width, height, role: 'img', 'aria-label': label, preserveAspectRatio: 'none', class: 'spark' },
    s('path', { d: area, fill: 'var(--ink-3)', 'fill-opacity': '0.08', stroke: 'none' }),
    s('path', { d: path, fill: 'none', stroke: 'var(--ink-3)', 'stroke-width': 1.5, 'stroke-linejoin': 'round', 'stroke-linecap': 'round', 'vector-effect': 'non-scaling-stroke' }),
    s('circle', { cx: x(values.length - 1), cy: y(last), r: 3.5, fill: color, stroke: 'var(--surface-1)', 'stroke-width': 2 }),
  );
}

/**
 * Stacked composition bar + legend (legend always shown; values as text, never colour alone).
 * @param {Array<{symbol:string, weight:number, label?:string}>} segments
 */
export function allocationBar(segments) {
  const visible = segments.filter((seg) => seg.weight > 0);
  const bar = h(
    'div',
    { class: 'alloc__bar', role: 'img', 'aria-label': visible.map((seg) => `${seg.symbol} ${seg.weight.toFixed(1)}%`).join('、') },
    visible.map((seg) =>
      h('span', {
        class: 'alloc__seg',
        title: `${seg.symbol} ${seg.weight.toFixed(1)}%`,
        style: { width: `${seg.weight}%`, background: SERIES[segments.indexOf(seg) % SERIES.length] },
      }),
    ),
  );
  const legend = h(
    'ul',
    { class: 'alloc__legend' },
    segments.map((seg, index) =>
      h(
        'li',
        { class: 'alloc__item' },
        h('span', { class: 'alloc__swatch', style: { background: SERIES[index % SERIES.length] } }),
        h('span', { class: 'mono', text: seg.symbol }),
        h('span', { class: 'muted num', text: `${seg.weight.toFixed(1)}%` }),
      ),
    ),
  );
  return h('div', { class: 'alloc' }, bar, legend);
}

/** Delta text with a direction class; colour plus a sign, never colour alone. */
export function delta(value, { pct = true, digits = 2, className = '' } = {}) {
  const tone = direction(value);
  return h('span', { class: `${tone} num ${className}`.trim(), text: pct ? fmtPct(value, digits) : String(value) });
}
