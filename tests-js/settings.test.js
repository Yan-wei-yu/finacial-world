import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mergeCosts, parseCost } from '../site/js/settings.js';

test('parseCost accepts positive numbers with thousand separators', () => {
  assert.equal(parseCost('8.5'), 8.5);
  assert.equal(parseCost('1,234.5'), 1234.5);
  assert.equal(parseCost('0'), null);
  assert.equal(parseCost('-3'), null);
  assert.equal(parseCost('abc'), null);
});

test('mergeCosts only touches symbols that had an input box', () => {
  const existing = { NOK: 8.5, SKHY: 120 };

  const { costs, invalid } = mergeCosts(existing, [
    { symbol: 'NOK', raw: '9' },
    { symbol: 'DRAM', raw: '' },
    { symbol: 'QNT', raw: '31.2' },
  ]);

  assert.deepEqual(costs, { NOK: 9, SKHY: 120, QNT: 31.2 });
  assert.deepEqual(invalid, []);
  assert.deepEqual(existing, { NOK: 8.5, SKHY: 120 }); // not mutated
});

test('mergeCosts clears a cost when its box is emptied and reports bad input', () => {
  const { costs, invalid } = mergeCosts({ NOK: 8.5 }, [
    { symbol: 'NOK', raw: '' },
    { symbol: 'DRAM', raw: '-1' },
  ]);

  assert.deepEqual(costs, {});
  assert.deepEqual(invalid, ['DRAM']);
});

test('opening settings with no holdings loaded keeps every saved cost', () => {
  assert.deepEqual(mergeCosts({ NOK: 8.5, SKHY: 120 }, []).costs, { NOK: 8.5, SKHY: 120 });
});
