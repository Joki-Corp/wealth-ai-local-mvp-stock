from typing import List, Tuple
from collections import defaultdict
from src.logger import StageLogger
from src.schemas import NormalizedStockPosition


def _completeness_score(pos: NormalizedStockPosition) -> int:
    """Calculate a quality score based on verification and non-null fields."""
    score = 0
    if pos.is_verified:
        score += 100

    fields = [
        pos.lots,
        pos.shares,
        pos.avg_price,
        pos.last_price,
        pos.market_value,
        pos.invested_value,
        pos.unrealized_pnl_nominal,
        pos.unrealized_pnl_pct,
    ]
    score += sum(1 for f in fields if f is not None)

    if pos.company_name:
        score += 1

    return score


def deduplicate_positions(
    positions: List[NormalizedStockPosition],
    logger: StageLogger = None,
) -> List[NormalizedStockPosition]:
    """
    Stage 6: Deduplicate cross-image overlapping stock holdings and resolve screen cutoffs.
    1. Exact Holding Match (ticker, lots, avg_price)
    2. Partial Cut-off Resolution
    3. Multi-broker / Distinct Holdings Preservation
    """
    if not positions:
        if logger:
            logger.log("No positions to deduplicate")
        return []

    initial_count = len(positions)
    merged_tickers = set()

    # Step 1: Exact holding match (ticker, lots, avg_price)
    exact_groups = defaultdict(list)
    unkeyed_positions = []

    for pos in positions:
        if pos.lots is not None and pos.avg_price is not None:
            # Round to avoid floating point mismatch
            key = (pos.ticker, round(pos.lots, 2), round(pos.avg_price, 2))
            exact_groups[key].append(pos)
        else:
            unkeyed_positions.append(pos)

    surviving_exact: List[NormalizedStockPosition] = []
    for key, group in exact_groups.items():
        if len(group) > 1:
            merged_tickers.add(key[0])
            # Pick the position with highest completeness score
            best_pos = max(group, key=_completeness_score)
            surviving_exact.append(best_pos)
        else:
            surviving_exact.append(group[0])

    candidates = surviving_exact + unkeyed_positions

    # Step 2: Partial Cut-off Resolution
    # Separate verified complete records from unverified incomplete ones per ticker
    by_ticker = defaultdict(list)
    for pos in candidates:
        by_ticker[pos.ticker].append(pos)

    final_positions: List[NormalizedStockPosition] = []

    for ticker, group in by_ticker.items():
        if len(group) == 1:
            final_positions.append(group[0])
            continue

        # Look for complete verified records
        verified = [p for p in group if p.is_verified]
        unverified = [p for p in group if not p.is_verified]

        retained: List[NormalizedStockPosition] = list(verified)

        for uv in unverified:
            is_partial_duplicate = False
            for v in verified:
                # Check if it matches any non-empty anchor
                lot_match = uv.lots is not None and v.lots is not None and abs(uv.lots - v.lots) < 0.01
                avg_match = uv.avg_price is not None and v.avg_price is not None and abs(uv.avg_price - v.avg_price) < 0.01
                market_match = uv.market_value is not None and v.market_value is not None and abs(uv.market_value - v.market_value) < 100.0

                if lot_match or avg_match or market_match:
                    is_partial_duplicate = True
                    merged_tickers.add(ticker)
                    break

            if not is_partial_duplicate:
                retained.append(uv)

        final_positions.extend(retained)

    # Sort final holdings by ticker
    final_positions.sort(key=lambda p: (p.ticker, p.broker_name or ""))

    final_count = len(final_positions)
    merged_count = initial_count - final_count

    if logger:
        if merged_count > 0:
            sample_merged = ", ".join(sorted(list(merged_tickers))[:5])
            if len(merged_tickers) > 5:
                sample_merged += f" (+{len(merged_tickers) - 5} more)"
            logger.log(
                f"Merged {merged_count} overlapping stock(s) ({sample_merged}) -> {final_count} unique holdings"
            )
        else:
            logger.log(f"No overlaps detected -> {final_count} unique holdings")

    return final_positions

