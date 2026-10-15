import { test } from 'node:test';
import assert from 'node:assert/strict';
import { isTradingDay, nextRegularOpen, sessionAt, zonedTimeToUtc } from '../site/js/market-clock.js';

const at = (iso) => new Date(iso);

test('regular session counts down to the close (DST)', () => {
  const session = sessionAt(at('2026-10-15T14:00:00Z'));
  assert.equal(session.phase, 'regular');
  assert.equal(session.label, '盤中');
  assert.equal(session.targetLabel, '收盤倒數');
  assert.equal(session.target.toISOString(), '2026-10-15T20:00:00.000Z');
});

test('pre-market counts down to the open', () => {
  const session = sessionAt(at('2026-10-15T12:00:00Z'));
  assert.equal(session.phase, 'pre');
  assert.equal(session.target.toISOString(), '2026-10-15T13:30:00.000Z');
});

test('after hours and overnight phases', () => {
  assert.equal(sessionAt(at('2026-10-15T21:00:00Z')).phase, 'post');
  const overnight = sessionAt(at('2026-10-16T02:00:00Z'));
  assert.equal(overnight.phase, 'overnight');
  assert.equal(overnight.target.toISOString(), '2026-10-16T13:30:00.000Z');
});

test('weekend is closed and the next open is Monday', () => {
  const saturday = at('2026-10-17T15:00:00Z');
  assert.equal(sessionAt(saturday).phase, 'closed');
  assert.equal(nextRegularOpen(saturday).toISOString(), '2026-10-19T13:30:00.000Z');
});

test('Friday night after the close is closed, not overnight', () => {
  assert.equal(sessionAt(at('2026-10-17T02:00:00Z')).phase, 'closed');
});

test('NYSE holidays are closed', () => {
  assert.equal(sessionAt(at('2026-11-26T16:00:00Z')).phase, 'closed');
  assert.equal(sessionAt(at('2026-11-26T16:00:00Z')).reason, '休市（假日）');
});

test('early close days end at 13:00 ET', () => {
  const session = sessionAt(at('2026-11-27T15:00:00Z'));
  assert.equal(session.phase, 'regular');
  assert.equal(session.target.toISOString(), '2026-11-27T18:00:00.000Z');
});

test('winter opens at 14:30 UTC after DST ends', () => {
  assert.equal(nextRegularOpen(at('2026-11-02T12:00:00Z')).toISOString(), '2026-11-02T14:30:00.000Z');
});

test('zonedTimeToUtc handles both offsets', () => {
  assert.equal(zonedTimeToUtc(2026, 3, 9, 9, 30, 'America/New_York').toISOString(), '2026-03-09T13:30:00.000Z');
  assert.equal(zonedTimeToUtc(2026, 12, 1, 9, 30, 'America/New_York').toISOString(), '2026-12-01T14:30:00.000Z');
});

test('isTradingDay respects weekends and holidays', () => {
  assert.equal(isTradingDay('2026-07-03'), false);
  assert.equal(isTradingDay('2026-10-15'), true);
  assert.equal(isTradingDay('2026-10-17'), false);
});

test('holiday rules keep working after the published calendar ends (2028)', () => {
  for (const day of ['2028-01-17', '2028-02-21', '2028-04-14', '2028-05-29', '2028-06-19', '2028-07-04', '2028-09-04', '2028-11-23', '2028-12-25']) {
    assert.equal(isTradingDay(day), false, day);
  }
  assert.equal(isTradingDay('2027-12-31'), true); // New Year's Day 2028 falls on a Saturday: no Friday holiday
  assert.equal(isTradingDay('2028-07-03'), true);
});

test('rule-derived holidays match the published NYSE calendar for 2026–2027', () => {
  const published = [
    '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03', '2026-09-07', '2026-11-26', '2026-12-25',
    '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18', '2027-07-05', '2027-09-06', '2027-11-25', '2027-12-24',
  ];
  for (const day of published) assert.equal(isTradingDay(day), false, day);
});

test('early-close days: 13:00 close, extended hours end at 17:00 ET', () => {
  assert.equal(sessionAt(at('2026-11-27T21:00:00Z')).phase, 'post');
  assert.equal(sessionAt(at('2026-11-27T22:30:00Z')).phase, 'closed');
  assert.equal(sessionAt(at('2028-07-03T16:30:00Z')).phase, 'regular');
  assert.equal(sessionAt(at('2028-07-03T17:30:00Z')).phase, 'post'); // 13:30 EDT on an early-close day
});
