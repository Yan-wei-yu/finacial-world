/** US equity session clock (NYSE rules, DST-aware). Pure, no DOM access. */
import { TZ_NEW_YORK, zonedParts } from './format.js';

const PRE_OPEN = 4 * 60;
const OPEN = 9 * 60 + 30;
const CLOSE = 16 * 60;
const EARLY_CLOSE = 13 * 60;
const POST_END = 20 * 60;
const EARLY_POST_END = 17 * 60; // late trading also ends early on half days
const LABELS = { pre: '盤前', regular: '盤中', post: '盤後', overnight: '夜盤', closed: '休市' };
const calendars = new Map();

const pad = (value) => String(value).padStart(2, '0');
const keyOf = (year, month, day) => `${year}-${pad(month)}-${pad(day)}`;
const splitKey = (key) => key.split('-').map(Number);
const weekdayOn = (year, month, day) => new Date(Date.UTC(year, month - 1, day)).getUTCDay();

function nthWeekday(year, month, weekday, n) {
  const first = weekdayOn(year, month, 1);
  return 1 + ((weekday - first + 7) % 7) + (n - 1) * 7;
}

function lastWeekday(year, month, weekday) {
  const lastDay = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return lastDay - ((weekdayOn(year, month, lastDay) - weekday + 7) % 7);
}

/** Gregorian Easter Sunday (Meeus / Jones / Butcher). @returns {[number, number]} [month, day] */
function easterSunday(year) {
  const a = year % 19;
  const b = Math.floor(year / 100);
  const c = year % 100;
  const d = Math.floor(b / 4);
  const e = b % 4;
  const f = Math.floor((b + 8) / 25);
  const g = Math.floor((b - f + 1) / 3);
  const h = (19 * a + b - d - g + 15) % 30;
  const i = Math.floor(c / 4);
  const k = c % 4;
  const l = (32 + 2 * e + 2 * i - h - k) % 7;
  const m = Math.floor((a + 11 * h + 22 * l) / 451);
  const month = Math.floor((h + l - 7 * m + 114) / 31);
  const day = ((h + l - 7 * m + 114) % 31) + 1;
  return [month, day];
}

function shiftDays(year, month, day, delta) {
  const date = new Date(Date.UTC(year, month - 1, day + delta));
  return keyOf(date.getUTCFullYear(), date.getUTCMonth() + 1, date.getUTCDate());
}

/** Saturday holidays move to Friday, Sunday holidays to Monday. */
function observed(year, month, day) {
  const weekday = weekdayOn(year, month, day);
  if (weekday === 6) return shiftDays(year, month, day, -1);
  if (weekday === 0) return shiftDays(year, month, day, 1);
  return keyOf(year, month, day);
}

function buildCalendar(year) {
  const holidays = new Set();
  const newYear = weekdayOn(year, 1, 1);
  if (newYear !== 6) holidays.add(newYear === 0 ? keyOf(year, 1, 2) : keyOf(year, 1, 1)); // no Friday holiday for a Saturday New Year
  holidays.add(keyOf(year, 1, nthWeekday(year, 1, 1, 3)));
  holidays.add(keyOf(year, 2, nthWeekday(year, 2, 1, 3)));
  const [easterMonth, easterDay] = easterSunday(year);
  holidays.add(shiftDays(year, easterMonth, easterDay, -2));
  holidays.add(keyOf(year, 5, lastWeekday(year, 5, 1)));
  holidays.add(observed(year, 6, 19));
  holidays.add(observed(year, 7, 4));
  holidays.add(keyOf(year, 9, nthWeekday(year, 9, 1, 1)));
  const thanksgiving = nthWeekday(year, 11, 4, 4);
  holidays.add(keyOf(year, 11, thanksgiving));
  holidays.add(observed(year, 12, 25));

  const earlyCloses = new Set([keyOf(year, 11, thanksgiving + 1)]);
  const july3 = weekdayOn(year, 7, 3);
  if (july3 >= 1 && july3 <= 4) earlyCloses.add(keyOf(year, 7, 3));
  const christmasEve = weekdayOn(year, 12, 24);
  if (christmasEve >= 1 && christmasEve <= 4) earlyCloses.add(keyOf(year, 12, 24));
  return { holidays, earlyCloses };
}

function calendarFor(year) {
  if (!calendars.has(year)) calendars.set(year, buildCalendar(year));
  return calendars.get(year);
}

const isHoliday = (key) => calendarFor(splitKey(key)[0]).holidays.has(key);
const isEarlyClose = (key) => calendarFor(splitKey(key)[0]).earlyCloses.has(key);

function weekdayOf(key) {
  const [y, m, d] = splitKey(key);
  return weekdayOn(y, m, d);
}

function shiftKey(key, days) {
  const [y, m, d] = splitKey(key);
  return shiftDays(y, m, d, days);
}

/** @param {string} key "YYYY-MM-DD" in New York @returns {boolean} */
export function isTradingDay(key) {
  const weekday = weekdayOf(key);
  return weekday >= 1 && weekday <= 5 && !isHoliday(key);
}

function offsetMinutes(date, timeZone) {
  const p = zonedParts(date, timeZone);
  return Math.round((Date.UTC(p.year, p.month - 1, p.day, p.hour, p.minute, p.second) - date.getTime()) / 60000);
}

/** Wall-clock time in a zone → UTC instant. @returns {Date} */
export function zonedTimeToUtc(year, month, day, hour, minute, timeZone) {
  const guess = Date.UTC(year, month - 1, day, hour, minute);
  const offset = offsetMinutes(new Date(guess), timeZone);
  const first = guess - offset * 60000;
  const corrected = offsetMinutes(new Date(first), timeZone);
  return new Date(corrected === offset ? first : guess - corrected * 60000);
}

function nyInstant(key, minutes) {
  const [y, m, d] = splitKey(key);
  return zonedTimeToUtc(y, m, d, Math.floor(minutes / 60), minutes % 60, TZ_NEW_YORK);
}

function nyNow(now) {
  const p = zonedParts(now, TZ_NEW_YORK);
  return { key: keyOf(p.year, p.month, p.day), minutes: p.hour * 60 + p.minute };
}

/** @param {Date} now @returns {Date} next 09:30 ET on a trading day */
export function nextRegularOpen(now) {
  const { key, minutes } = nyNow(now);
  let day = isTradingDay(key) && minutes < OPEN ? key : shiftKey(key, 1);
  while (!isTradingDay(day)) day = shiftKey(day, 1);
  return nyInstant(day, OPEN);
}

function phaseOf(key, minutes) {
  const trading = isTradingDay(key);
  const early = isEarlyClose(key);
  const close = early ? EARLY_CLOSE : CLOSE;
  const postEnd = early ? EARLY_POST_END : POST_END;
  if (trading && minutes >= OPEN && minutes < close) return 'regular';
  if (trading && minutes >= PRE_OPEN && minutes < OPEN) return 'pre';
  if (trading && minutes >= close && minutes < postEnd) return 'post';
  if (minutes >= POST_END && isTradingDay(shiftKey(key, 1))) return 'overnight';
  if (minutes < PRE_OPEN && trading) return 'overnight';
  return 'closed';
}

function closedReason(key) {
  if (isHoliday(key)) return '休市（假日）';
  const weekday = weekdayOf(key);
  return weekday === 0 || weekday === 6 ? '休市（週末）' : '休市';
}

/**
 * Session phase at an instant plus the countdown target.
 * @param {Date} now
 * @returns {{phase:string, label:string, reason:string|null, target:Date, targetLabel:string}}
 */
export function sessionAt(now) {
  const { key, minutes } = nyNow(now);
  const phase = phaseOf(key, minutes);
  const regular = phase === 'regular';
  return {
    phase,
    label: LABELS[phase],
    reason: phase === 'closed' ? closedReason(key) : null,
    target: regular ? nyInstant(key, isEarlyClose(key) ? EARLY_CLOSE : CLOSE) : nextRegularOpen(now),
    targetLabel: regular ? '收盤倒數' : '開盤倒數',
  };
}
