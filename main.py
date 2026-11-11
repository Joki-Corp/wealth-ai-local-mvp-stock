import datetime
import sys
import time
from pathlib import Path
from typing import List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import (
    ASSETS_DIR,
    PROCESSED_ASSETS_DIR,
    OUTPUT_DIR,
    OUTPUT_JSON_FILE,
    OLLAMA_MODEL,
    SUPPORTED_EXTENSIONS,
)
from src.logger import console, stage_timer
from src.schemas import (
    AssetSourceSummary,
    NormalizedStockPosition,
    WealthAggregatorResult,
)
from src.stage1_gatekeeper import process_gatekeeper
from src.stage2_ocr import process_ocr
from src.stage3_spatial import process_spatial
from src.stage4_llm import process_llm_extraction
from src.stage5_normalizer import process_normalization
from src.stage6_deduplicator import deduplicate_positions


def format_idr(val: Optional[float]) -> str:
    """Format float into Indonesian Rupiah currency string (e.g. Rp 47.500.000)."""
    if val is None:
        return "-"
    formatted = f"{int(round(val)):,}".replace(",", ".")
    return f"Rp {formatted}"


def format_price(val: Optional[float]) -> str:
    """Format stock unit price (e.g. 9.100)."""
    if val is None:
        return "-"
    return f"{int(round(val)):,}".replace(",", ".")


def format_pnl(nominal: Optional[float], pct: Optional[float]) -> str:
    """Format PnL nominal and percentage with colored styling."""
    if nominal is None and pct is None:
        return "-"

    nom_str = format_idr(nominal) if nominal is not None else "-"
    pct_str = f"{pct:+.2f}%" if pct is not None else ""

    combined = f"{nom_str} ({pct_str})" if pct_str else nom_str

    if nominal is not None:
        if nominal > 0:
            return f"[bold green]+{combined}[/bold green]" if not combined.startswith("+") else f"[bold green]{combined}[/bold green]"
        elif nominal < 0:
            return f"[bold red]{combined}[/bold red]"
    return combined


def render_wealth_hero(grand_total: float, total_invested: float, total_pnl: float, total_pct: float) -> None:
    """Render the primary Grand Total Net Worth Banner."""
    pnl_color = "bold green" if total_pnl >= 0 else "bold red"
    pnl_sign = "+" if total_pnl > 0 else ""
    pnl_text = f"[{pnl_color}]{pnl_sign}{format_idr(total_pnl)} ({pnl_sign}{total_pct:.2f}%)[/{pnl_color}]"

    banner_text = (
        f"\n[bold white]TOTAL NILAI KEKAYAAN BERSIH[/bold white]\n"
        f"[bold yellow on black]  {format_idr(grand_total)}  [/bold yellow on black]\n\n"
        f"Total Modal: [bold]{format_idr(total_invested)}[/bold]   •   Total Laba/Rugi: {pnl_text}\n"
    )

    console.print()
    console.print(
        Panel(
            banner_text,
            title="[bold green]💰 RINGKASAN TOTAL KEKAYAAN (NET WORTH)[/bold green]",
            border_style="green",
            expand=True,
        )
    )


def render_sources_breakdown_table(sources: List[AssetSourceSummary]) -> None:
    """Render the Breakdown Table showing where the wealth comes from."""
    table = Table(
        title="[bold cyan]RINCIAN SUMBER KEKAYAAN (ASSET SOURCES BREAKDOWN)[/bold cyan]",
        header_style="bold cyan",
        show_lines=True,
    )

    table.add_column("No", justify="center", style="dim", width=4)
    table.add_column("Sumber / Broker", justify="left", style="bold white")
    table.add_column("File Screenshot", justify="left", style="dim")
    table.add_column("Nilai Aset (Market Value)", justify="right", style="bold yellow")
    table.add_column("Modal (Invested)", justify="right")
    table.add_column("Laba / Rugi (PnL)", justify="right")
    table.add_column("Portofolio", justify="center", style="cyan")

    grand_market = sum(s.total_market_value for s in sources)
    grand_invested = sum(s.total_invested_value for s in sources)
    grand_pnl = sum(s.total_pnl_nominal for s in sources)
    grand_pct = (grand_pnl / grand_invested * 100.0) if grand_invested > 0 else 0.0
    grand_positions = sum(s.positions_count for s in sources)

    for idx, s in enumerate(sources, start=1):
        broker_label = s.broker_name or "Portofolio Saham"
        table.add_row(
            str(idx),
            broker_label,
            s.source_file,
            format_idr(s.total_market_value),
            format_idr(s.total_invested_value),
            format_pnl(s.total_pnl_nominal, s.total_pnl_pct),
            f"{s.positions_count} saham",
        )

    # Total row
    table.add_row(
        "",
        "[bold]TOTAL KESELURUHAN[/bold]",
        f"[dim]{len(sources)} Sumber[/dim]",
        f"[bold yellow]{format_idr(grand_market)}[/bold yellow]",
        f"[bold]{format_idr(grand_invested)}[/bold]",
        format_pnl(grand_pnl, grand_pct),
        f"[bold cyan]{grand_positions} saham[/bold cyan]",
        style="bold on black",
    )

    console.print()
    console.print(table)


def render_portfolio_table(positions: List[NormalizedStockPosition]) -> None:
    """Render the detailed underlying stock holdings table."""
    table = Table(
        title="[bold dim]DETAIL KEPEMILIKAN SAHAM (UNDERLYING HOLDINGS)[/bold dim]",
        header_style="bold magenta",
        show_lines=True,
    )

    table.add_column("No", justify="center", style="dim", width=4)
    table.add_column("Ticker", justify="center", style="bold yellow")
    table.add_column("Lot", justify="right")
    table.add_column("Shares", justify="right")
    table.add_column("Avg Price", justify="right")
    table.add_column("Last Price", justify="right")
    table.add_column("Invested Value", justify="right")
    table.add_column("Market Value", justify="right")
    table.add_column("Unrealized PnL", justify="right")
    table.add_column("Status", justify="center")
    table.add_column("Sumber", justify="left", style="dim")

    for idx, pos in enumerate(positions, start=1):
        lot_str = f"{pos.lots:g}" if pos.lots is not None else "-"
        shares_str = f"{pos.shares:,}".replace(",", ".") if pos.shares is not None else "-"
        avg_str = format_price(pos.avg_price)
        last_str = format_price(pos.last_price)
        invested_str = format_idr(pos.invested_value)
        market_str = format_idr(pos.market_value)
        pnl_str = format_pnl(pos.unrealized_pnl_nominal, pos.unrealized_pnl_pct)

        status_str = "[bold green]✅ OK[/bold green]" if pos.is_verified else "[bold yellow]⚠️ Check[/bold yellow]"
        source_str = f"{pos.broker_name or ''} ({pos.source_file})".strip()

        table.add_row(
            str(idx),
            pos.ticker,
            lot_str,
            shares_str,
            avg_str,
            last_str,
            invested_str,
            market_str,
            pnl_str,
            status_str,
            source_str,
        )

    console.print()
    console.print(table)


def run_pipeline() -> None:
    """Execute the wealth aggregation and stock portfolio extraction pipeline."""
    console.print("\n[bold]=== LOCAL WEALTH AGGREGATOR & PORTFOLIO EXTRACTOR (macOS Vision + Ollama) ===[/bold]\n")

    # Pre-flight check: Assets folder check
    if not ASSETS_DIR.exists():
        ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    available_files = [
        f for f in ASSETS_DIR.iterdir()
        if not f.name.startswith(".") and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if not available_files:
        console.print(
            Panel(
                f"[yellow]Tidak ada file screenshot di folder '{ASSETS_DIR}'.[/yellow]\n\n"
                f"Silakan letakkan screenshot aset ({', '.join(sorted(SUPPORTED_EXTENSIONS))}) "
                f"ke dalam folder [bold]{ASSETS_DIR}[/bold] lalu jalankan kembali.",
                title="[bold yellow]Folder Assets Kosong[/bold yellow]",
                border_style="yellow",
            )
        )
        return

    overall_t0 = time.perf_counter()

    try:
        # [STAGE 1/6] Gatekeeper & Image Prep
        with stage_timer(1, 6, "Gatekeeper & Image Prep") as stage1:
            prepared_images = process_gatekeeper(
                assets_dir=ASSETS_DIR,
                processed_dir=PROCESSED_ASSETS_DIR,
                logger=stage1,
            )

        if not prepared_images:
            console.print("[yellow]Tidak ada gambar baru setelah deduplikasi. Selesai.[/yellow]")
            return

        # [STAGE 2/6] Apple Vision OCR
        with stage_timer(2, 6, "Apple Vision OCR (ocrmac)") as stage2:
            ocr_results = process_ocr(prepared_images, logger=stage2)

        # [STAGE 3/6] Spatial Row Clustering
        with stage_timer(3, 6, "Spatial Row Clustering") as stage3:
            spatial_results = process_spatial(ocr_results, logger=stage3)

        # [STAGE 4/6] Local LLM Extraction
        with stage_timer(4, 6, f"Local LLM Extraction ({OLLAMA_MODEL}, think=False)") as stage4:
            llm_outputs = process_llm_extraction(spatial_results, logger=stage4)

        # [STAGE 5/6] Normalization & Math Validation
        with stage_timer(5, 6, "Normalization & Math Validation") as stage5:
            normalized_positions, source_metadata = process_normalization(llm_outputs, logger=stage5)

        # [STAGE 6/6] Cross-Image Deduplication
        with stage_timer(6, 6, "Cross-Image Deduplication") as stage6:
            final_positions = deduplicate_positions(normalized_positions, logger=stage6)

    except Exception as e:
        console.print(f"\n[bold red]Pipeline terhenti karena error:[/bold red] {e}\n")
        sys.exit(1)

    overall_duration = time.perf_counter() - overall_t0

    # Group positions by source file to compute per-source wealth
    sources_summary: List[AssetSourceSummary] = []
    positions_by_source = {}
    for p in final_positions:
        positions_by_source.setdefault(p.source_file, []).append(p)

    # Also handle sources that might have header total but 0 parsed positions
    all_source_files = set(list(positions_by_source.keys()) + list(source_metadata.keys()))

    for src_file in sorted(all_source_files):
        src_positions = positions_by_source.get(src_file, [])
        meta = source_metadata.get(src_file, {})
        broker = meta.get("broker_name")
        header_tot = meta.get("header_total")

        pos_market = sum(p.market_value for p in src_positions if p.market_value is not None)
        pos_invested = sum(p.invested_value for p in src_positions if p.invested_value is not None)

        # If individual market values are present, use their sum; otherwise fallback to header_total if available
        effective_market = pos_market if pos_market > 0 else (header_tot or 0.0)
        effective_invested = pos_invested if pos_invested > 0 else effective_market

        pnl_nom = sum(p.unrealized_pnl_nominal for p in src_positions if p.unrealized_pnl_nominal is not None)
        if pnl_nom == 0.0 and effective_market > 0 and effective_invested > 0:
            pnl_nom = effective_market - effective_invested

        pnl_pct = (pnl_nom / effective_invested * 100.0) if effective_invested > 0 else 0.0
        verified_cnt = sum(1 for p in src_positions if p.is_verified)

        sources_summary.append(
            AssetSourceSummary(
                source_file=src_file,
                broker_name=broker,
                header_total=header_tot,
                total_market_value=round(effective_market, 2),
                total_invested_value=round(effective_invested, 2),
                total_pnl_nominal=round(pnl_nom, 2),
                total_pnl_pct=round(pnl_pct, 2),
                positions_count=len(src_positions),
                verified_count=verified_cnt,
            )
        )

    # Grand totals
    grand_wealth = sum(s.total_market_value for s in sources_summary)
    grand_invested = sum(s.total_invested_value for s in sources_summary)
    grand_pnl = grand_wealth - grand_invested
    grand_pct = (grand_pnl / grand_invested * 100.0) if grand_invested > 0 else 0.0

    # Render Wealth Overview
    render_wealth_hero(grand_wealth, grand_invested, grand_pnl, grand_pct)
    render_sources_breakdown_table(sources_summary)
    if final_positions:
        render_portfolio_table(final_positions)

    # Export Result Dataset
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    result_data = WealthAggregatorResult(
        generated_at=datetime.datetime.now().isoformat(),
        grand_total_wealth=round(grand_wealth, 2),
        grand_total_invested=round(grand_invested, 2),
        grand_total_pnl_nominal=round(grand_pnl, 2),
        grand_total_pnl_pct=round(grand_pct, 2),
        total_positions_count=len(final_positions),
        sources_count=len(sources_summary),
        sources=sources_summary,
        holdings=final_positions,
        execution_time_seconds=round(overall_duration, 3),
    )

    with open(OUTPUT_JSON_FILE, "w", encoding="utf-8") as f:
        f.write(result_data.model_dump_json(indent=2))

    console.print(f"\n[dim]Data tersimpan ke JSON:[/dim] [cyan]{OUTPUT_JSON_FILE}[/cyan]\n")


if __name__ == "__main__":
    run_pipeline()

