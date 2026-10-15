/** Portfolio math. Pure functions that never mutate their inputs. */
import { isNum } from './format.js';

const sum = (values) => values.reduce((total, value) => total + value, 0);
const numOrNull = (value) => (isNum(value) ? value : null);

/**
 * @param {Array<{symbol:string, shares:number, cost?:number|null}>} holdings
 * @param {Record<string, any>} quotes quote snapshot keyed by symbol
 * @param {Record<string, number>} [costOverrides] per-browser cost basis (never published)
 */
export function buildPositions(holdings, quotes, costOverrides = {}) {
  return holdings.map((holding) => {
    const quote = quotes?.[holding.symbol] ?? null;
    const price = numOrNull(quote?.price);
    const prev = numOrNull(quote?.prev_close);
    const override = costOverrides?.[holding.symbol];
    const cost = isNum(override) && override > 0 ? override : numOrNull(holding.cost);
    const extPrice = numOrNull(quote?.ext?.price);
    return {
      ...holding,
      quote,
      price,
      prev,
      cost,
      value: price !== null ? price * holding.shares : null,
      prevValue: prev !== null ? prev * holding.shares : null,
      dayChange: price !== null && prev !== null ? (price - prev) * holding.shares : null,
      dayChangePct: numOrNull(quote?.change_pct),
      extPrice,
      extLabel: quote?.ext?.label ?? null,
      extChangePct: numOrNull(quote?.ext?.change_pct),
      extValue: extPrice !== null ? extPrice * holding.shares : null,
      pnl: cost !== null && price !== null ? (price - cost) * holding.shares : null,
      pnlPct: cost !== null && price !== null ? (price / cost - 1) * 100 : null,
      stale: Boolean(quote?.stale),
    };
  });
}

/** @param {ReturnType<typeof buildPositions>} positions */
export function summarize(positions) {
  const priced = positions.filter((p) => p.value !== null);
  const total = sum(priced.map((p) => p.value));
  const prevTotal = sum(priced.map((p) => p.prevValue ?? p.value));
  const dayChange = total - prevTotal;
  const extTotal = priced.some((p) => p.extValue !== null) ? sum(priced.map((p) => p.extValue ?? p.value)) : null;
  const withCost = priced.filter((p) => p.pnl !== null);
  const costBasis = withCost.length ? sum(withCost.map((p) => p.cost * p.shares)) : null;
  const pnl = withCost.length ? sum(withCost.map((p) => p.pnl)) : null;
  return {
    total,
    prevTotal,
    dayChange,
    dayChangePct: prevTotal > 0 ? (dayChange / prevTotal) * 100 : null,
    extTotal,
    extChange: extTotal !== null ? extTotal - total : null,
    extChangePct: extTotal !== null && total > 0 ? ((extTotal - total) / total) * 100 : null,
    costBasis,
    pnl,
    pnlPct: costBasis ? (pnl / costBasis) * 100 : null,
    weights: positions.map((p) => ({ symbol: p.symbol, weight: total > 0 && p.value !== null ? (p.value / total) * 100 : 0 })),
    pricedCount: priced.length,
    count: positions.length,
  };
}
