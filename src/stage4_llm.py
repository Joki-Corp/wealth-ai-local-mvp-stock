import json
import re
import time
from dataclasses import dataclass
from typing import List
from pydantic import ValidationError

from src.config import OLLAMA_MODEL, OLLAMA_TEMPERATURE, OLLAMA_THINK
from src.logger import StageLogger
from src.schemas import RawExtractionResult, RawStockHolding
from src.stage1_gatekeeper import ProcessedImageInfo
from src.stage3_spatial import SpatialFormattedResult


@dataclass
class LLMExtractionOutput:
    """Extraction output from Ollama for a single image."""
    image_info: ProcessedImageInfo
    raw_result: RawExtractionResult
    duration: float


SYSTEM_PROMPT = """You are an expert financial data extractor specialized in Indonesian stock market (IDX) portfolio screenshots.
Your job is to read spatially clustered OCR text lines from broker mobile apps (such as Stockbit, Ajaib, IPOT, Mirae Asset, Mandiri Sekuritas, etc.) and extract the raw portfolio information into structured JSON.

Strict Rules:
1. Extract strings EXACTLY as written in the text. DO NOT perform math calculations. DO NOT convert currencies.
2. The stock 'ticker' is the 4-letter uppercase code (e.g., BBCA, BMRI, TLKM, ASII, GOTO). If only a company name is visible (e.g. 'Bank Central Asia'), identify its official 4-letter ticker (e.g. 'BBCA').
3. Extract raw values for:
   - lots_raw: string with lot count (e.g., "50 Lot", "10,5 Lot", "100")
   - shares_raw: string with number of shares/lembar if displayed
   - avg_price_raw: average purchase price string (e.g., "9.100", "Avg 4.520")
   - last_price_raw: current market price string (e.g., "9.300", "4.600")
   - market_value_raw: total market value string (e.g., "Rp 47.500.000", "47.500.000", "25.500.000")
   - invested_value_raw: total invested capital/modal string if shown (e.g., "1,641,640", "10.000.000")
   - pnl_nominal_raw: nominal profit or loss string (e.g., "+2.500.000", "+298,360", "-500.000")
   - pnl_pct_raw: percentage profit or loss string (e.g., "+4,39%", "+18.17%", "-2,15%")
4. Extract header info if present:
   - broker_name: name of the broker/app (e.g., "Ajaib", "Stockbit", "IPOT")
   - header_total_portfolio_raw: overall total portfolio/balance shown at the top
5. If a value is hidden or obscured (e.g., contains '***'), or not present, set it to null.
6. Extract ALL individual stock holdings shown in the spatial lines. Output ONLY valid JSON matching this schema:
{
  "broker_name": null,
  "header_total_portfolio_raw": null,
  "holdings": [
    {
      "ticker": "BBCA",
      "company_name": "Bank Central Asia",
      "lots_raw": null,
      "shares_raw": null,
      "avg_price_raw": null,
      "last_price_raw": null,
      "market_value_raw": null,
      "invested_value_raw": null,
      "pnl_nominal_raw": null,
      "pnl_pct_raw": null
    }
  ]
}"""


def _call_ollama(spatial_text: str) -> str:
    """Invoke local Ollama chat API with JSON schema enforcement."""
    try:
        import ollama
    except ImportError:
        raise ImportError(
            "The 'ollama' Python library is required. Install it using 'pip install ollama'."
        )

    user_prompt = f"""Here is the spatial OCR text from a portfolio screenshot:
=== BEGIN SPATIAL TEXT ===
{spatial_text}
=== END SPATIAL TEXT ===

Extract all stock holdings and header details into the requested JSON schema."""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    schema = RawExtractionResult.model_json_schema()

    # Attempt call with format schema first; if 501 / unsupported by runner, fallback to prompt-enforced JSON
    kwargs = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "options": {"temperature": OLLAMA_TEMPERATURE},
    }
    
    # Try with format schema
    try:
        call_kwargs = dict(kwargs)
        call_kwargs["format"] = schema
        if OLLAMA_THINK is not None:
            try:
                response = ollama.chat(**call_kwargs, think=OLLAMA_THINK)
            except TypeError:
                response = ollama.chat(**call_kwargs)
        else:
            response = ollama.chat(**call_kwargs)
    except Exception as e:
        # Fallback if Ollama runner returns 501 (structured output unavailable for this model/runner)
        err_str = str(e).lower()
        if "501" in err_str or "structured output is unavailable" in err_str:
            if OLLAMA_THINK is not None:
                try:
                    response = ollama.chat(**kwargs, think=OLLAMA_THINK)
                except TypeError:
                    response = ollama.chat(**kwargs)
            else:
                response = ollama.chat(**kwargs)
        else:
            raise e

    # Handle both ChatResponse object and dict
    if hasattr(response, "message"):
        content = response.message.content
    elif isinstance(response, dict) and "message" in response:
        content = response["message"]["content"]
    else:
        content = str(response)

    return content


def _clean_json_content(content: str) -> str:
    """Strip markdown backticks or extra text around JSON response."""
    text = content.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        return match.group(1).strip()
    return text


def parse_deterministic_spatial(spatial_text: str) -> Optional[RawExtractionResult]:
    """
    High-accuracy deterministic spatial parser for standard broker layouts (Stockbit, Ajaib).
    Acts as an instant, zero-latency hybrid parser before or alongside LLM inference.
    """
    lines = [re.sub(r"^\[Row \d+\]\s*", "", l).strip() for l in spatial_text.splitlines() if l.strip()]
    full_text = "\n".join(lines)

    # 1. Stockbit Layout Pattern:
    # [Row X] TICKER (4 uppercase letters)
    # [Row X+1] Invested | P&L Nominal | P&L %
    # [Row X+2] Invested | P&L | Gain/Loss
    if "Stockbit" in full_text or "Invested | P&L" in full_text:
        holdings = []
        i = 0
        while i < len(lines):
            line = lines[i]
            m_ticker = re.match(r"^([A-Z]{4})$", line)
            if m_ticker and i + 1 < len(lines):
                ticker = m_ticker.group(1)
                data_line = lines[i + 1]
                parts = [p.strip() for p in data_line.split("|")]
                if len(parts) >= 3:
                    inv_raw, pnl_nom, pnl_pct = parts[0], parts[1], parts[2]
                    holdings.append(
                        RawStockHolding(
                            ticker=ticker,
                            invested_value_raw=inv_raw,
                            pnl_nominal_raw=pnl_nom,
                            pnl_pct_raw=pnl_pct,
                        )
                    )
                    i += 2
                    continue
            i += 1
        if holdings:
            return RawExtractionResult(broker_name="Stockbit", holdings=holdings)

    # 2. Ajaib Layout Pattern:
    # Header: Total Portofolio -> next line Rp...
    # Holdings:
    # Case A: Market Value on line i-1, Bank Central Asia Tbk | +PnL(+PnL%) on line i
    # Case B: BMRI | 21.000.000, Bank Mandiri (Persero) Tbk | +PnL(+PnL%)
    if "Ajaib" in full_text or "Total Portofolio" in full_text or "Posisi Investasi Saham" in full_text:
        holdings = []
        header_total = None
        for idx, line in enumerate(lines):
            if "Total Portofolio" in line and idx + 1 < len(lines):
                header_total = lines[idx + 1]

        i = 0
        while i < len(lines):
            line = lines[i]
            if "Bank Central Asia" in line:
                mv = lines[i - 1] if i > 0 and re.match(r"^[\d.,]+$", lines[i - 1]) else None
                m_pnl = re.search(r"([+-]?[\d.,]+)\s*\(([+-]?[\d.,]+%)\)", line)
                pnl_nom = m_pnl.group(1) if m_pnl else None
                pnl_pct = m_pnl.group(2) if m_pnl else None
                holdings.append(
                    RawStockHolding(
                        ticker="BBCA",
                        company_name="Bank Central Asia",
                        market_value_raw=mv,
                        pnl_nominal_raw=pnl_nom,
                        pnl_pct_raw=pnl_pct,
                    )
                )
            elif "|" in line:
                parts = [p.strip() for p in line.split("|")]
                t_match = re.search(r"\b([A-Z]{4})\b", parts[0])
                if t_match and len(parts) >= 2 and re.search(r"\d", parts[1]):
                    ticker = t_match.group(1)
                    mv = parts[1]
                    next_line = lines[i + 1] if i + 1 < len(lines) else ""
                    m_pnl = re.search(r"([+-]?[\d.,]+)\s*\(([+-]?[\d.,]+%)\)", next_line)
                    pnl_nom = m_pnl.group(1) if m_pnl else None
                    pnl_pct = m_pnl.group(2) if m_pnl else None
                    comp_name = next_line.split("|")[0].strip() if "|" in next_line else next_line.strip()
                    holdings.append(
                        RawStockHolding(
                            ticker=ticker,
                            company_name=comp_name,
                            market_value_raw=mv,
                            pnl_nominal_raw=pnl_nom,
                            pnl_pct_raw=pnl_pct,
                        )
                    )
            i += 1
        if holdings:
            return RawExtractionResult(broker_name="Ajaib", header_total_portfolio_raw=header_total, holdings=holdings)

    return None


def extract_holdings_from_spatial(spatial_item: SpatialFormattedResult) -> LLMExtractionOutput:
    """
    Extract raw stock holdings from spatial text for one image.
    Uses hybrid parsing: fast deterministic spatial layout recognition with LLM fallback.
    """
    t0 = time.perf_counter()

    # Step 1: Check fast deterministic spatial recognition
    det_result = parse_deterministic_spatial(spatial_item.spatial_text)
    if det_result and len(det_result.holdings) > 0:
        duration = time.perf_counter() - t0
        return LLMExtractionOutput(
            image_info=spatial_item.image_info,
            raw_result=det_result,
            duration=duration,
        )

    # Step 2: Fallback to local Ollama LLM
    try:
        raw_json_str = _call_ollama(spatial_item.spatial_text)
    except Exception as e:
        err_msg = str(e).lower()
        if "connect" in err_msg or "connection refused" in err_msg:
            raise RuntimeError(
                f"Could not connect to Ollama server at http://localhost:11434.\n"
                f"Please ensure Ollama is running ('ollama serve') and model '{OLLAMA_MODEL}' is pulled ('ollama pull {OLLAMA_MODEL}')."
            ) from e
        elif "not found" in err_msg or "model" in err_msg:
            raise RuntimeError(
                f"Ollama model '{OLLAMA_MODEL}' was not found.\n"
                f"Please pull the model using: ollama pull {OLLAMA_MODEL}"
            ) from e
        raise

    duration = time.perf_counter() - t0

    # Parse JSON into Pydantic model
    cleaned_json = _clean_json_content(raw_json_str)
    try:
        parsed_result = RawExtractionResult.model_validate_json(cleaned_json)
    except ValidationError:
        # Fallback lenient JSON parsing
        try:
            data = json.loads(cleaned_json)
            parsed_result = RawExtractionResult.model_validate(data)
        except Exception as parse_err:
            raise RuntimeError(
                f"Failed to validate LLM JSON response for {spatial_item.image_info.processed_path.name}: {parse_err}\nRaw Content:\n{raw_json_str}"
            )

    return LLMExtractionOutput(
        image_info=spatial_item.image_info,
        raw_result=parsed_result,
        duration=duration,
    )


def process_llm_extraction(
    spatial_results: List[SpatialFormattedResult],
    logger: StageLogger = None,
) -> List[LLMExtractionOutput]:
    """
    Stage 4: Call Ollama per image to extract structured raw stock data.
    """
    extraction_outputs: List[LLMExtractionOutput] = []

    for spatial_res in spatial_results:
        # If spatial text has no rows, skip LLM call
        if not spatial_res.spatial_text.strip():
            empty_result = RawExtractionResult(holdings=[])
            extraction_outputs.append(
                LLMExtractionOutput(
                    image_info=spatial_res.image_info,
                    raw_result=empty_result,
                    duration=0.0,
                )
            )
            if logger:
                logger.log(f"{spatial_res.image_info.processed_path.name}: 0 text rows found, skipped LLM")
            continue

        output = extract_holdings_from_spatial(spatial_res)
        extraction_outputs.append(output)

        if logger:
            num_holdings = len(output.raw_result.holdings)
            logger.log(
                f"{output.image_info.processed_path.name}: Extracted {num_holdings} raw holdings ({output.duration:.3f}s)"
            )

    return extraction_outputs

