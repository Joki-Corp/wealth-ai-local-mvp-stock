from typing import List, Optional
from pydantic import BaseModel, Field


class RawStockHolding(BaseModel):
    """Raw extracted stock holding before numeric normalization."""
    ticker: Optional[str] = Field(
        default=None,
        description="4-letter stock ticker code in uppercase, e.g. BBCA, TLKM, BMRI."
    )
    company_name: Optional[str] = Field(
        default=None,
        description="Company full or partial name, e.g. Bank Central Asia."
    )
    lots_raw: Optional[str] = Field(
        default=None,
        description="Raw lot quantity string as seen on screen, e.g. '50 Lot', '10.5'."
    )
    shares_raw: Optional[str] = Field(
        default=None,
        description="Raw shares quantity string if displayed, e.g. '5,000 Lembar'."
    )
    avg_price_raw: Optional[str] = Field(
        default=None,
        description="Raw average buy price string, e.g. 'Avg 9.100' or '9100'."
    )
    last_price_raw: Optional[str] = Field(
        default=None,
        description="Raw current/last market price string, e.g. '9.500'."
    )
    market_value_raw: Optional[str] = Field(
        default=None,
        description="Raw total current market value string, e.g. 'Rp 47.500.000'."
    )
    invested_value_raw: Optional[str] = Field(
        default=None,
        description="Raw total invested capital string if shown directly, e.g. '1,641,640'."
    )
    pnl_nominal_raw: Optional[str] = Field(
        default=None,
        description="Raw nominal unrealized profit/loss string, e.g. '+2.000.000' or '-500.000'."
    )
    pnl_pct_raw: Optional[str] = Field(
        default=None,
        description="Raw percentage unrealized profit/loss string, e.g. '+4,39%' or '-1.25%'."
    )


class RawExtractionResult(BaseModel):
    """Pydantic schema passed to Ollama for structured JSON generation."""
    broker_name: Optional[str] = Field(
        default=None,
        description="Name of the broker or app if visible (e.g. Ajaib, Stockbit, IPOT, Mirae)."
    )
    header_total_portfolio_raw: Optional[str] = Field(
        default=None,
        description="Total portfolio value string shown at the top header, if present."
    )
    holdings: List[RawStockHolding] = Field(
        default_factory=list,
        description="List of stock holdings parsed from the spatial text."
    )


class AssetSourceSummary(BaseModel):
    """Wealth summary broken down per image or asset source."""
    source_file: str
    broker_name: Optional[str] = None
    header_total: Optional[float] = None
    total_market_value: float
    total_invested_value: float
    total_pnl_nominal: float
    total_pnl_pct: float
    positions_count: int
    verified_count: int


class NormalizedStockPosition(BaseModel):
    """Clean, mathematically validated, and deduplicated stock position."""
    ticker: str
    company_name: Optional[str] = None
    lots: Optional[float] = None
    shares: Optional[int] = None
    avg_price: Optional[float] = None
    last_price: Optional[float] = None
    invested_value: Optional[float] = None
    market_value: Optional[float] = None
    unrealized_pnl_nominal: Optional[float] = None
    unrealized_pnl_pct: Optional[float] = None
    is_verified: bool = False
    broker_name: Optional[str] = None
    source_file: str


class WealthAggregatorResult(BaseModel):
    """
    Final exported Net Worth & Wealth Aggregator dataset.
    Focuses on Grand Total Wealth, breakdown by sources, and underlying holdings.
    """
    generated_at: str
    grand_total_wealth: float
    grand_total_invested: float
    grand_total_pnl_nominal: float
    grand_total_pnl_pct: float
    total_positions_count: int
    sources_count: int
    sources: List[AssetSourceSummary]
    holdings: List[NormalizedStockPosition]
    execution_time_seconds: float


# Alias for backward compatibility
PortfolioResult = WealthAggregatorResult

