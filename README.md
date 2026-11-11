# Local Net Worth & Wealth Aggregator MVP (macOS Native Pipeline)

A fast, offline, and privacy-preserving Python CLI tool for macOS (Apple Silicon M-Series) that extracts and aggregates **Total Net Worth** from screenshots of multiple asset sources (stock portfolios like `Ajaib`, `Stockbit`, `IPOT`, `Mirae Asset`, etc.) using Apple's native Vision framework (`ocrmac`), deterministic spatial coordinate clustering, and a local LLM via Ollama (`qwen3.5:2b`).

---

## 🎯 Main Goal & Core Value

The primary purpose of this tool is to provide:
1. **Jumlah Total Kekayaan (Grand Total Net Worth):** Satu angka total nilai kekayaan bersih dari gabungan seluruh aset yang dimasukkan.
2. **Daftar Rincian Sumber Aset (Source Breakdown):** Tabel transparan yang menunjukkan total kekayaan tersebut bersumber dari mana saja (misal: Ajaib Rp 61.205.600, Stockbit Rp 12.500.000).
3. **Audit Transparan (Underlying Holdings):** Rincian kepemilikan saham di tiap akun untuk verifikasi matematis ($1\text{ Lot} = 100\text{ Lembar}$, Modal, Nilai Pasar, PnL).

---

## 🚀 Features

- **100% Local & Offline**: All OCR and LLM reasoning runs directly on your Mac. No data leaves your machine.
- **Native Apple Vision OCR**: Uses macOS `VNRecognizeTextRequest` via `ocrmac` with `accurate` mode.
- **Dual-Locale Number Parser**: Accurately parses both Indonesian dot-thousands (`21.000.000`) and English comma-thousands (`1,641,640`).
- **Algebraic Imputation Engine**: Solves $\text{Market Value} = \text{Invested} + \text{PnL}$ and calculates missing variables dynamically.
- **Cross-Image Deduplication**: Reconciles scrolling screenshot overlaps across multiple captures.
- **Rich Wealth UI & JSON Export**: Prominent Total Wealth Hero Banner, Asset Sources Breakdown Table, and clean JSON export in `./output/portfolio_result.json`.

---

## 📁 Directory Structure

```text
stock-extractor-mvp/
├── assets/                     # Place raw screenshots here (.png, .jpg, .jpeg, .heic, .webp)
├── processed_assets/           # Converted RGB .png images & chunks for ocrmac
├── output/                     # Exported final JSON results (portfolio_result.json)
├── src/
│   ├── __init__.py
│   ├── config.py               # Constants, thresholds, and model configurations
│   ├── logger.py               # Custom Rich logger with context-manager stage timers
│   ├── schemas.py              # Pydantic v2 data models
│   ├── stage1_gatekeeper.py    # MD5 & pHash deduplication, HEIC conversion, chunking
│   ├── stage2_ocr.py           # Native Apple Vision OCR wrapper (ocrmac)
│   ├── stage3_spatial.py       # Deterministic row coordinate clustering
│   ├── stage4_llm.py           # Ollama client with schema enforcement
│   ├── stage5_normalizer.py    # IDR string parsing, math imputation, verification
│   └── stage6_deduplicator.py  # Cross-image scroll overlap deduplication
├── main.py                     # CLI entrypoint & Rich table/summary renderer
├── requirements.txt            # Python dependencies
├── ARCHITECTURE_FLOW.md        # Visual architecture flowcharts & concept guide for teams
├── PROJECT_CONTEXT.md          # Architectural guide & AI Agent specifications
└── README.md                   # This user guide
```

- For complete visual diagrams and pipeline flowcharts, see [ARCHITECTURE_FLOW.md](file:///Users/bayualif/Documents/referensi/nativemacdev/stock-extractor-mvp/ARCHITECTURE_FLOW.md).
- For AI development guidelines and domain context, see [PROJECT_CONTEXT.md](file:///Users/bayualif/Documents/referensi/nativemacdev/stock-extractor-mvp/PROJECT_CONTEXT.md).

---

## 🛠️ Prerequisites & Setup

### 1. Requirements
- macOS (Apple Silicon M1/M2/M3/M4 recommended)
- Python 3.10+
- [Ollama](https://ollama.com/) installed

### 2. Install & Start Ollama
Start Ollama and download the `qwen3.5:2b` model:
```bash
# Start Ollama service (if not already running)
ollama serve

# In a separate terminal, pull the model
ollama pull qwen3.5:2b
```

### 3. Create Python Virtual Environment
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

## 🖥️ Usage

1. Place your portfolio screenshots inside the `./assets` directory:
   ```bash
   cp ~/Downloads/my_portfolio*.png ./assets/
   ```

2. Run the pipeline:
   ```bash
   python main.py
   ```

3. View terminal logs, progress timers, and the final portfolio table:
   ```text
   [STEP 1/6] Gatekeeper & Image Prep .......................... DONE (0.042s)
      ├─ Loaded 2 files from /.../assets
      └─ Converted 2 unique image(s) to RGB PNG in processed_assets
   [STEP 2/6] Apple Vision OCR (ocrmac) ........................ DONE (0.195s)
      ├─ ajaib.png: Extracted 36 text boxes (0.098s)
      └─ stockbit.png: Extracted 42 text boxes (0.097s)
   [STEP 3/6] Spatial Row Clustering ........................... DONE (0.004s)
   ...
   ```

4. The final verified portfolio dataset is automatically saved to:
   ```text
   ./output/portfolio_result.json
   ```

---

## ⚙️ Configuration

You can customize thresholds in [src/config.py](file:///Users/bayualif/Documents/referensi/nativemacdev/stock-extractor-mvp/src/config.py):
- `PHASH_CUTOFF`: Hamming distance for perceptual duplicate detection (default: `2`).
- `LONG_IMAGE_ASPECT_RATIO`: Ratio triggering vertical slice chunking (default: `3.0`).
- `Y_TOLERANCE`: Normalized vertical tolerance for row grouping (default: `0.015`).
- `OLLAMA_MODEL`: Target Ollama model (default: `"qwen3.5:2b"`).
- `MATH_TOLERANCE_PCT` & `MATH_TOLERANCE_NOMINAL`: Margin for self-verification checks.

