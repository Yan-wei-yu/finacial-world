/** Pure helpers for the news panel (unit-tested in Node). */

/** A filter from the URL is only honoured when it names a known category or holding. */
export function validFilter(filter, categories, symbols) {
  if (filter === 'all' || typeof filter !== 'string') return 'all';
  if (filter.startsWith('sym:')) return symbols.includes(filter.slice(4)) ? filter : 'all';
  return Object.prototype.hasOwnProperty.call(categories, filter) ? filter : 'all';
}

/** How far back the list actually goes, e.g. "近 12 小時" / "近 3 天". */
export function spanLabel(items, now) {
  const times = items.map((item) => Date.parse(item.published)).filter(Number.isFinite);
  if (!times.length) return '';
  const hours = Math.max(1, Math.round((now.getTime() - Math.min(...times)) / 3_600_000));
  return hours < 48 ? `近 ${hours} 小時` : `近 ${Math.round(hours / 24)} 天`;
}
