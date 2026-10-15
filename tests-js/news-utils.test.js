import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spanLabel, validFilter } from '../site/js/news-utils.js';

test('validFilter falls back to "all" for unknown filters', () => {
  const categories = { semis: '半導體', macro: '總經' };
  const symbols = ['NOK', 'SKHY'];
  assert.equal(validFilter('semis', categories, symbols), 'semis');
  assert.equal(validFilter('sym:SKHY', categories, symbols), 'sym:SKHY');
  assert.equal(validFilter('sym:ZZZ', categories, symbols), 'all');
  assert.equal(validFilter('bogus', categories, symbols), 'all');
  assert.equal(validFilter('constructor', categories, symbols), 'all');
});

test('spanLabel describes how far back the list goes', () => {
  const now = new Date('2026-10-15T13:00:00Z');
  assert.equal(spanLabel([{ published: '2026-10-15T01:00:00Z' }, { published: '2026-10-15T12:00:00Z' }], now), '近 12 小時');
  assert.equal(spanLabel([{ published: '2026-10-12T13:00:00Z' }], now), '近 3 天');
  assert.equal(spanLabel([], now), '');
});
