import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildPositions, summarize } from '../site/js/portfolio.js';

const near = (actual, expected, tolerance = 1e-6) =>
  assert.ok(Math.abs(actual - expected) < tolerance, `${actual} != ${expected}`);

const holdings = [
  { symbol: 'NOK', shares: 820, cost: null },
  { symbol: 'SKHY', shares: 3, cost: 120 },
];
const quotes = {
  NOK: { price: 9.4, prev_close: 9.85, change_pct: -4.57, ext: { label: '盤後', price: 9.18, change_pct: -2.34 } },
  SKHY: { price: 147.55, prev_close: 157.06, change_pct: -6.06, ext: null, stale: true },
};

test('positions compute value, day change and P/L', () => {
  const [nok, skhy] = buildPositions(holdings, quotes, {});
  near(nok.value, 7708);
  near(nok.dayChange, -369);
  assert.equal(nok.pnl, null);
  assert.equal(nok.extLabel, '盤後');
  near(skhy.pnl, 82.65);
  near(skhy.pnlPct, 22.958333);
  assert.equal(skhy.stale, true);
});

test('a local cost basis overrides the config value', () => {
  const [nok] = buildPositions(holdings, quotes, { NOK: 8 });
  near(nok.pnl, 1148);
  assert.equal(nok.cost, 8);
});

test('positions do not mutate their inputs', () => {
  const frozen = Object.freeze(holdings.map((h) => Object.freeze({ ...h })));
  assert.doesNotThrow(() => buildPositions(frozen, quotes, {}));
});

test('summary totals, weights and extended-hours estimate', () => {
  const summary = summarize(buildPositions(holdings, quotes, {}));
  near(summary.total, 8150.65);
  near(summary.dayChange, -397.53);
  near(summary.dayChangePct, (-397.53 / 8548.18) * 100);
  near(summary.weights[0].weight, (7708 / 8150.65) * 100);
  near(summary.extTotal, 7970.25);
  near(summary.extChange, -180.4);
  assert.equal(summary.costBasis, 360);
  near(summary.pnl, 82.65);
  near(summary.pnlPct, (82.65 / 360) * 100);
});

test('missing quotes are excluded from totals', () => {
  const summary = summarize(buildPositions(holdings, { NOK: quotes.NOK }, {}));
  near(summary.total, 7708);
  assert.equal(summary.pricedCount, 1);
  assert.equal(summary.count, 2);
  assert.equal(summary.costBasis, null);
});

test('empty portfolio is safe', () => {
  const summary = summarize([]);
  assert.equal(summary.total, 0);
  assert.equal(summary.dayChangePct, null);
  assert.equal(summary.extTotal, null);
});
