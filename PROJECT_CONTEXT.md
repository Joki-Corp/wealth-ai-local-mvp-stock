# PROJECT_CONTEXT.md: Local Net Worth & Wealth Aggregator

> **Tujuan Dokumen Ini:**
> Dokumen ini adalah *Single Source of Truth* arsitektur, domain context, dan panduan teknis bagi developer maupun AI Coding Agent (Antigravity, Cursor, Claude Code, dll.) untuk memahami dan memperluas kapabilitas sistem ini tanpa merusak konvensi modular yang sudah ada.

---

## 1. Visi & Tujuan Utama (Project Vision)

Aplikasi ini adalah **Local Net Worth & Wealth Aggregator** berbasis CLI untuk macOS (Apple Silicon M-Series).
Aplikasi ini membaca *batch screenshots* dari folder `./assets/` (yang bisa berasal dari berbagai aplikasi finansial: sekuritas saham, reksadana, crypto, e-wallet, atau m-banking) dan menghasilkan:
1. **Grand Total Net Worth:** Total akumulasi nilai kekayaan bersih dari semua akun.
2. **Asset Sources Breakdown ("List total itu dari mana saja"):** Rincian transparan yang menunjukkan kontribusi nilai tiap sumber/akun (misal: Ajaib Rp 61.205.600, Stockbit Rp 12.500.000).
3. **Underlying Asset Audit:** Detail kepemilikan aset di balik angka-angka tersebut untuk transparansi audit.

### Filosofi Sistem:
- **100% Offline & Private:** Tidak ada byte data finansial atau gambar yang dikirim ke cloud.
- **Native Apple Silicon Acceleration:** Menggunakan framework Apple Vision (`ocrmac`) dan local Metal LLM via Ollama (`qwen3.5:2b`).
- **Deterministic Math Validation:** LLM hanya bertugas sebagai *text-to-json extractor*, sedangkan kalkulasi matematika dan validasi dikerjakan secara deterministik oleh Python.

---

## 2. Tech Stack

- **OS Target:** macOS (Apple Silicon M-Series)
- **Runtime:** Python 3.10+
- **OCR Engine:** Apple Vision (`VNRecognizeTextRequest` via `ocrmac`, level: `accurate`)
- **Local LLM:** Ollama model `qwen3.5:2b` (`temperature=0.0`, `think=False`)
- **Image Processing & Perceptual Hashing:** `Pillow`, `pillow-heif` (dukungan `.HEIC`), `imagehash`
- **Data Schemas & Validation:** `pydantic` (v2)
- **Terminal UI & Timer:** `rich`

---

## 3. Struktur Direktori Modular

```text
stock-extractor-mvp/
├── assets/                     # Folder input: Letakkan screenshot di sini (.png, .jpg, .heic, .webp)
├── processed_assets/           # Cache gambar hasil konversi RGB .png siap OCR & chunking
├── output/                     # Hasil export JSON akhir (portfolio_result.json)
├── src/
│   ├── __init__.py
│   ├── config.py               # Konstanta, paths, threshold pHash (<=2), Y-tolerance (0.015), model config
│   ├── logger.py               # Custom Rich logger dengan stopwatch per stage & formatting ranting
│   ├── schemas.py              # Pydantic v2 data models (Raw, Normalized, SourceSummary, WealthAggregatorResult)
│   ├── stage1_gatekeeper.py    # MD5 & pHash deduplikasi, konversi format, chunking screenshot panjang
│   ├── stage2_ocr.py           # Apple Vision OCR wrapper (ocrmac)
│   ├── stage3_spatial.py       # Algoritma clustering baris spasial (inversi koordinat Vision)
│   ├── stage4_llm.py           # Ekstraksi terstruktur LLM (Ollama qwen3.5:2b, schema enforcement & 501 fallback)
│   ├── stage5_normalizer.py    # Dual-locale parser (IDR dot & comma), imputasi aljabar, self-verification
│   └── stage6_deduplicator.py  # Rekonsiliasi scrolling screenshot overlap & partial edge cutoff
├── main.py                     # Entrypoint CLI, Hero Net Worth Banner, breakdown table, export JSON
├── requirements.txt            # Dependensi tersemat
├── README.md                   # Panduan cepat untuk pengguna manusia
└── PROJECT_CONTEXT.md          # Dokumen ini (spesifikasi & arsitektur proyek)
```

---

## 4. Pipeline 6 Tahap (End-to-End Architecture)

Setiap tahapan dibungkus oleh `stage_timer()` di [src/logger.py](file:///Users/bayualif/Documents/referensi/nativemacdev/stock-extractor-mvp/src/logger.py) yang mencetak waktu eksekusi dalam detik (`X.XXXs`).

### Stage 1: Gatekeeper & Pre-processor (`stage1_gatekeeper.py`)
1. Scan `./assets` untuk file `.jpg`, `.jpeg`, `.png`, `.heic`, `.webp` (abaikan `.DS_Store`).
2. **MD5 Hash Deduplication:** Drop file duplikat identik secara instan.
3. **Perceptual Hash (pHash):** Hitung Hamming distance menggunakan `imagehash.phash()`. Jika distance $\le 2$, drop sebagai duplikat visual.
4. **Standardisasi Format:** Konversi format non-RGB (seperti `.HEIC` dari iPhone atau RGBA) menjadi RGB `.png` di `./processed_assets/`.
5. **Scrolling Screenshot Chunking:** Jika rasio tinggi/lebar $\text{height}/\text{width} > 3.0$, potong gambar secara horizontal dengan overlap 15% agar akurasi OCR terjaga.

### Stage 2: Apple Vision OCR (`stage2_ocr.py`)
1. Jalankan `ocrmac.OCR(image_path, recognition_level="accurate").recognize()`.
2. Hasilkan list `(text, confidence, [x, y, w, h])`.
3. Filter noise jika `confidence < 0.4`.

### Stage 3: Spatial Coordinate Clustering (`stage3_spatial.py`)
*Aturan penting: Jangan kirim teks mentah tanpa struktur ke LLM.*
1. Koordinat Apple Vision berpusat di **kiri-bawah** (`(0,0)` di bottom-left). Inversi sumbu Y menjadi top-down:
   $$\text{top\_down\_y\_center} = 1.0 - (y + h/2.0)$$
2. **Row Clustering:** Kelompokkan teks yang memiliki selisih $\text{y\_center} \le \text{Y\_TOLERANCE}$ (`0.015`) ke dalam baris horizontal yang sama.
3. **Column Sorting:** Urutkan baris dari atas ke bawah, dan di dalam baris urutkan kiri ke kanan (`x` ascending).
4. Format output baris:
   ```text
   [Row 01] Portofolio | Order | Riwayat
   [Row 02] ADRO
   [Row 03] 1,641,640 | +298,360 | +18.17%
   ```

### Stage 4: Local LLM Structured Extraction (`stage4_llm.py`)
1. Satu panggilan LLM per satu screenshot.
2. Parameter:
   - `model="qwen3.5:2b"`
   - `think=False` (wajib untuk menjaga respons cepat dan mematikan token `<think>`)
   - `temperature=0.0`
   - Skema Pydantic `RawExtractionResult` (dengan fallback aman jika runner mengembalikan status 501).
3. **Aturan Ekstraksi:**
   - Ekstrak teks apa adanya: `ticker`, `company_name`, `lots_raw`, `shares_raw`, `avg_price_raw`, `last_price_raw`, `market_value_raw`, `invested_value_raw`, `pnl_nominal_raw`, `pnl_pct_raw`.
   - Jika kode ticker 4 huruf tidak tercetak eksplisit namun nama emiten ada (misal: "Bank Central Asia Tbk"), model diarahkan mengidentifikasi ticker resminya ("BBCA").
   - Dilarang menyuruh LLM melakukan kalkulasi matematika.

### Stage 5: Normalization & Algebraic Imputation (`stage5_normalizer.py`)
1. **Dual-Locale Number Sanitizer (`parse_idr_number`):**
   - Mendukung format Indonesia: titik ribuan `21.000.000`, koma desimal `+4,39%`.
   - Mendukung format Internasional: koma ribuan `1,641,640`, titik desimal `+18.17%`.
   - Menangani nilai tersensor (`***`), tanda minus, dan tanda kurung akuntansi `(500.000)`.
2. **Validasi Ticker:** Memastikan kode saham terdiri dari 4 huruf kapital (`regex \b([A-Z]{4})\b`).
3. **Algebraic Imputation Engine ($1\text{ Lot} = 100\text{ Lembar}$):**
   - $\text{Shares} = \text{Lot} \times 100$
   - $\text{Invested Value} = \text{Shares} \times \text{Avg Price}$
   - $\text{Market Value} = \text{Invested Value} + \text{Unrealized PnL}$ (Penting untuk broker seperti Stockbit)
   - $\text{Invested Value} = \text{Market Value} - \text{Unrealized PnL}$ (Penting untuk broker seperti Ajaib)
   - $\text{Last Price} = \text{Market Value} / \text{Shares}$
   - $\text{PnL \%} = (\text{Unrealized PnL} / \text{Invested Value}) \times 100$
4. **Self-Verification (`is_verified`):**
   - Lolos jika $(\text{Shares} \times \text{Last Price} \approx \text{Market Value})$ ATAU $(\text{Invested} + \text{PnL} \approx \text{Market Value})$ dengan toleransi selisih $\le \text{Rp } 5.000$ atau $< 1\%$.

### Stage 6: Cross-Image Deduplicator (`stage6_deduplicator.py`)
1. **Exact Holding Match:** Jika record memiliki `(ticker, lots, avg_price)` yang sama di beberapa gambar (overlap scrolling), pertahankan 1 record yang paling lengkap (`is_verified=True`).
2. **Partial Edge Cutoff Resolution:** Jika ada baris terpotong di tepi layar (banyak field `None`) tetapi ada baris identik yang lengkap di screenshot sambungannya, drop baris yang terpotong.
3. **Multi-Broker Preservation:** Jika saham sama dimiliki di broker berbeda (lots atau modal berbeda dan keduanya valid), pertahankan keduanya.

---

## 5. Standar Output & Tampilan

Aplikasi menampilkan:
1. **Hero Net Worth Banner:** Total Nilai Kekayaan Bersih, Total Modal, dan Total PnL (Nominal & %).
2. **Asset Sources Breakdown Table:** Menampilkan daftar tiap akun/file sumber, nilai asetnya, modal, dan laba/ruginya.
3. **Underlying Holdings Table:** Tabel detail per saham.
4. **JSON Export:** Disimpan ke [output/portfolio_result.json](file:///Users/bayualif/Documents/referensi/nativemacdev/stock-extractor-mvp/output/portfolio_result.json) dengan skema `WealthAggregatorResult`.

---

## 6. Panduan Pengembangan di Masa Depan (Extensibility for AI Agents)

Jika Anda atau AI Agent diminta menambahkan jenis aset baru di masa mendatang:
1. **Aset Reksadana (Bibit / Bareksa):**
   - Tambahkan skema di [src/schemas.py](file:///Users/bayualif/Documents/referensi/nativemacdev/stock-extractor-mvp/src/schemas.py): `fund_name`, `units_raw`, `nav_raw`, `market_value_raw`.
   - Rumus imputasi: $\text{Market Value} = \text{Units} \times \text{NAV}$.
2. **Aset Crypto (Indodax / Tokocrypto):**
   - Ticker crypto (misal: `BTC`, `ETH`, `SOL`).
   - Imputasi: $\text{Market Value} = \text{Coin Amount} \times \text{Price IDR}$.
3. **Aset Kas / Rekening Bank (BCA / Mandiri / Jago):**
   - Cukup ekstrak `account_name` dan `available_balance_raw`.
   - $\text{Market Value} = \text{Balance}$, $\text{PnL} = 0$.

Semua modul dirancang modular agar *source breakdown* dapat mengagregasi semua jenis aset tersebut ke dalam satu angka **Grand Total Wealth**.

