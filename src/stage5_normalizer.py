import re
from typing import Dict, List, Optional, Tuple
from src.config import (
    SHARES_PER_LOT,
    MATH_TOLERANCE_PCT,
    MATH_TOLERANCE_NOMINAL,
)
from src.logger import StageLogger
from src.schemas import RawStockHolding, NormalizedStockPosition
from src.stage4_llm import LLMExtractionOutput


def parse_idr_number(val: Optional[str]) -> Optional[float]:
    """
    Deterministically sanitize and parse Indonesian and English formatted financial numbers:
    - Indonesian dot-thousands (Ajaib): 'Rp 47.500.000', '9.100', '+4,39%', '10,5 Lot'
    - OCR mixed separator (Ajaib): '+2.107,500' -> 2107500.0
    - English comma-thousands (Stockbit): '1,641,640', '+298,360', '+18.17%'
    - Accounting negatives: '(500.000)' -> -500000.0
    - Censored / masked: '***', '--' -> None
    """
    if val is None:
        return None

    raw = str(val).strip()
    if not raw or raw in {"-", "--", "N/A", "null", "None"}:
        return None

    # Obscured / masked values
    if any(c in raw for c in ["*", "•", "x", "X"]):
        return None

    # Detect negative signs or accounting parentheses: (1.000)
    is_negative = (raw.startswith("(") and raw.endswith(")")) or "-" in raw

    # Remove currency prefixes, units, signs, and percentage symbols
    cleaned = re.sub(r"(?i)\b(rp\.?|idr\.?|lot|lembar|lbr|shares?)\b", "", raw)
    cleaned = cleaned.replace("Rp.", "").replace("rp.", "").replace("Rp", "").replace("rp", "")
    cleaned = cleaned.replace("+", "").replace("-", "").replace("%", "").replace("(", "").replace(")", "").strip()
    cleaned = cleaned.strip(" .,")
    cleaned = cleaned.replace(" ", "")

    if not cleaned:
        return None

    # Split by both dot and comma
    parts = re.split(r"[.,]", cleaned)
    if len(parts) > 1:
        # Check if every part after the first consists of exactly 3 digits
        # (e.g. 2.107,500 or 1,641,640 or 25.500.000 or 5,600)
        if all(len(p) == 3 for p in parts[1:]):
            cleaned = "".join(parts)
        else:
            # The last part is decimal (1 or 2 digits, e.g. 4,39 or 18.17 or 3,7 or 10,5)
            int_part = "".join(parts[:-1])
            dec_part = parts[-1]
            cleaned = f"{int_part}.{dec_part}"

    try:
        num = float(cleaned)
        return -num if is_negative else num
    except ValueError:
        return None


def clean_ticker(ticker_raw: Optional[str]) -> Optional[str]:
    """
    Validate and extract standard 4-letter uppercase IDX stock ticker (e.g. BBCA, BMRI).
    Filters out noise or non-ticker words.
    """
    if not ticker_raw:
        return None

    candidate = ticker_raw.strip().upper()
    match = re.search(r"\b([A-Z]{4})\b", candidate)
    if match:
        return match.group(1)
    return None


def normalize_holding(
    raw: RawStockHolding,
    source_file: str,
    broker_name: Optional[str] = None,
) -> Optional[NormalizedStockPosition]:
    """
    Normalize a single RawStockHolding:
    - Cleans ticker
    - Parses numbers
    - Mathematical imputation (shares, invested_value, last_price, unrealized_pnl)
    - Verifies math consistency
    """
    ticker = clean_ticker(raw.ticker)
    if not ticker:
        # Must have a valid 4-letter ticker
        return None

    company_name = raw.company_name.strip() if raw.company_name else None

    lots = parse_idr_number(raw.lots_raw)
    shares_parsed = parse_idr_number(raw.shares_raw)
    shares = int(shares_parsed) if shares_parsed is not None else None

    # Guard: if a huge number was put in lots_raw without "lot" keyword, it is actually invested_value
    invested_value_parsed = parse_idr_number(getattr(raw, "invested_value_raw", None))
    if lots is not None and lots > 50000 and invested_value_parsed is None and "lot" not in str(raw.lots_raw).lower():
        invested_value_parsed = lots
        lots = None
        shares = None

    avg_price = parse_idr_number(raw.avg_price_raw)
    last_price = parse_idr_number(raw.last_price_raw)
    market_value = parse_idr_number(raw.market_value_raw)
    pnl_nominal = parse_idr_number(raw.pnl_nominal_raw)
    pnl_pct = parse_idr_number(raw.pnl_pct_raw)

    # 1. Lot <-> Shares imputation (only if lots was legitimately present)
    if lots is not None and shares is None:
        shares = int(round(lots * SHARES_PER_LOT))
    elif shares is not None and lots is None:
        lots = round(shares / float(SHARES_PER_LOT), 2)

    # 2. Invested Value calculation & Imputation
    invested_value: Optional[float] = invested_value_parsed
    if invested_value is None and shares is not None and avg_price is not None:
        invested_value = round(shares * avg_price, 2)
    elif invested_value is None and market_value is not None and pnl_nominal is not None:
        invested_value = round(market_value - pnl_nominal, 2)

    # 3. Market Value and Last Price imputation
    if market_value is None and shares is not None and last_price is not None:
        market_value = round(shares * last_price, 2)
    elif market_value is None and invested_value is not None and pnl_nominal is not None:
        market_value = round(invested_value + pnl_nominal, 2)
    elif last_price is None and market_value is not None and shares is not None and shares > 0:
        last_price = round(market_value / shares, 2)

    # 4. Unrealized PnL imputation
    if pnl_nominal is None and market_value is not None and invested_value is not None:
        pnl_nominal = round(market_value - invested_value, 2)

    if pnl_pct is None and pnl_nominal is not None and invested_value is not None and invested_value > 0:
        pnl_pct = round((pnl_nominal / invested_value) * 100.0, 2)

    # 5. Self-Verification Check
    is_verified = False
    
    # Check 1: shares * last_price vs market_value
    if shares is not None and last_price is not None and market_value is not None:
        expected_market = shares * last_price
        diff = abs(expected_market - market_value)
        rel_diff = diff / market_value if market_value > 0 else 0
        if diff <= MATH_TOLERANCE_NOMINAL or rel_diff <= MATH_TOLERANCE_PCT:
            is_verified = True
    
    # Check 2: invested_value + pnl_nominal vs market_value
    if not is_verified and invested_value is not None and pnl_nominal is not None and market_value is not None:
        expected_market = invested_value + pnl_nominal
        diff = abs(expected_market - market_value)
        if diff <= MATH_TOLERANCE_NOMINAL:
            is_verified = True

    return NormalizedStockPosition(
        ticker=ticker,
        company_name=company_name,
        lots=lots,
        shares=shares,
        avg_price=avg_price,
        last_price=last_price,
        invested_value=invested_value,
        market_value=market_value,
        unrealized_pnl_nominal=pnl_nominal,
        unrealized_pnl_pct=pnl_pct,
        is_verified=is_verified,
        broker_name=broker_name,
        source_file=source_file,
    )


def process_normalization(
    llm_outputs: List[LLMExtractionOutput],
    logger: StageLogger = None,
) -> Tuple[List[NormalizedStockPosition], dict]:
    """
    Stage 5: Sanitize numbers, impute missing math values, and verify positions.
    Returns normalized positions and per-source metadata (broker name, header balance).
    """
    normalized_positions: List[NormalizedStockPosition] = []
    source_metadata: dict = {}

    for item in llm_outputs:
        source_name = item.image_info.original_filename
        broker = item.raw_result.broker_name
        header_total = parse_idr_number(item.raw_result.header_total_portfolio_raw)

        source_metadata[source_name] = {
            "broker_name": broker,
            "header_total": header_total,
        }

        for raw_holding in item.raw_result.holdings:
            norm_pos = normalize_holding(raw_holding, source_file=source_name, broker_name=broker)
            if norm_pos:
                normalized_positions.append(norm_pos)

    if logger:
        verified_count = sum(1 for p in normalized_positions if p.is_verified)
        logger.log(f"Normalized {len(normalized_positions)} positions ({verified_count} mathematically verified)")

    return normalized_positions, source_metadata

