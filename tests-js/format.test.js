import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  daysUntil,
  direction,
  fmtCompactZh,
  fmtCountdown,
  fmtDate,
  fmtDateTime,
  fmtMoney,
  fmtPct,
  fmtPrice,
  fmtRevenue,
  fmtShares,
  fmtSigned,
  relativeTime,
} from '../site/js/format.js';

test('fmtPrice scales decimals with magnitude', () => {
  assert.equal(fmtPrice(9.4), '9.40');
  assert.equal(fmtPrice(26692.87), '26,692.87');
  assert.equal(fmtPrice(0.12345), '0.1235');
  assert.equal(fmtPrice(1262000), '1,262,000');
  assert.equal(fmtPrice(null), '—');
  assert.equal(fmtPrice(Number.NaN), '—');
});

test('fmtPct and fmtSigned use a typographic minus', () => {
  assert.equal(fmtPct(1.234), '+1.23%');
  assert.equal(fmtPct(-4.567), '−4.57%');
  assert.equal(fmtPct(0), '0.00%');
  assert.equal(fmtPct(undefined), '—');
  assert.equal(fmtSigned(-0.45), '−0.45');
  assert.equal(fmtSigned(12.3, 1), '+12.3');
});

test('fmtMoney formats USD and TWD', () => {
  assert.equal(fmtMoney(12793.4, 'USD'), 'US$12,793');
  assert.equal(fmtMoney(414600, 'TWD'), 'NT$414,600');
  assert.equal(fmtMoney(-120.5, 'USD', 2), '−US$120.50');
  assert.equal(fmtMoney(null, 'USD'), '—');
});

test('fmtShares keeps fractional shares readable', () => {
  assert.equal(fmtShares(820), '820');
  assert.equal(fmtShares(0.5), '0.5');
  assert.equal(fmtShares(1234.5678), '1,234.5678');
});

test('fmtCompactZh uses 萬 / 億 / 兆', () => {
  assert.equal(fmtCompactZh(5066953280), '50.67 億');
  assert.equal(fmtCompactZh(99673624820000), '99.67 兆');
  assert.equal(fmtCompactZh(15000), '1.5 萬');
  assert.equal(fmtCompactZh(950), '950');
  assert.equal(fmtCompactZh(-25000), '−2.5 萬');
});

test('fmtRevenue appends the currency name', () => {
  assert.equal(fmtRevenue(5066953280, 'EUR'), '50.67 億歐元');
  assert.equal(fmtRevenue(99673624820000, 'KRW'), '99.67 兆韓元');
  assert.equal(fmtRevenue(1e9, 'XYZ'), '10 億 XYZ');
  assert.equal(fmtRevenue(null, 'USD'), '—');
});

test('direction maps sign to rise / fall / flat', () => {
  assert.equal(direction(0.5), 'rise');
  assert.equal(direction(-0.1), 'fall');
  assert.equal(direction(0), 'flat');
  assert.equal(direction(null), 'flat');
});

test('fmtDateTime renders Taipei time with weekday', () => {
  assert.equal(fmtDateTime('2026-10-28T18:00:00Z'), '10/29 (四) 02:00');
  assert.equal(fmtDateTime('nope'), '—');
});

test('fmtDate renders calendar dates without timezone drift', () => {
  assert.equal(fmtDate('2026-10-22'), '10/22 (四)');
  assert.equal(fmtDate('bad'), '—');
});

test('relativeTime speaks Chinese', () => {
  const now = new Date('2026-10-15T13:00:00Z');
  assert.equal(relativeTime('2026-10-15T12:59:30Z', now), '剛剛');
  assert.equal(relativeTime('2026-10-15T12:15:00Z', now), '45 分鐘前');
  assert.equal(relativeTime('2026-10-15T08:00:00Z', now), '5 小時前');
  assert.equal(relativeTime('2026-10-13T10:00:00Z', now), '2 天前');
});

test('fmtCountdown switches to days for long waits', () => {
  assert.equal(fmtCountdown(3_723_000), '1:02:03');
  assert.equal(fmtCountdown(90_061_000), '1 天 1 小時');
  assert.equal(fmtCountdown(-5), '0:00:00');
});

test('daysUntil counts Taipei calendar days', () => {
  const now = new Date('2026-10-15T13:00:00Z');
  assert.equal(daysUntil('2026-10-15', now), 0);
  assert.equal(daysUntil('2026-10-22', now), 7);
  assert.equal(daysUntil('2026-10-14', now), -1);
});
