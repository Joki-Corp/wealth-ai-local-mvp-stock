# 📊 Flowchart Singkat Alur Aplikasi

Berikut flowchart ringkas untuk presentasi konsep dan cara kerja aplikasi ke tim:

```mermaid
flowchart TD
    %% Input
    A["📱 Raw Screenshots<br/>(Ajaib, Stockbit, IPOT, dll.)"] --> B["1. Gatekeeper<br/>• Drop Duplikat (MD5 & pHash)<br/>• Konversi ke RGB PNG"]

    %% OCR
    B --> C["2. Native Apple Vision OCR<br/>• Ekstrak Bounding Box & Teks<br/>• Filter Noise (Conf >= 0.4)"]

    %% SPATIAL CLUSTERING (KUNCI AKURASI)
    C --> D["3. Spatial Clustering ⭐<br/>• Inversi Sumbu Y: Vision (0,0 Kiri-Bawah) -> Top-Down<br/>• Kelompokkan Teks Sebaris (Y-Tolerance 0.015)<br/>• Urutkan Kolom Kiri ke Kanan (X-Ascending)"]

    %% HYBRID EXTRACTION
    D --> E{"4. Hybrid Extractor"}
    E -- "Layout Dikenal<br/>(Stockbit / Ajaib)" --> F["⚡ Fast-Path (0.000s)<br/>Ekstraksi Spasial Presisi 100%"]
    E -- "Layout Baru" --> G["🤖 Local LLM (qwen3.5:2b)<br/>Prompt JSON Schema Enforcement"]

    %% NORMALIZER & MATH
    F --> H["5. Normalizer & Aljabar Finansial<br/>• Dual-Locale Parser (Titik/Koma/Shorthand Jt/M/rb)<br/>• Market Value = Invested + PnL<br/>• Verifikasi Matematika (✅ OK)"]
    G --> H

    %% DEDUPLIKASI & OUTPUT
    H --> I["6. Cross-Image Deduplicator<br/>Merge Overlap Scrolling Screenshot"]
    I --> J["🎯 OUTPUT AKHIR"]

    %% OUTPUT DETAIL
    J --> K["💰 Grand Total Net Worth<br/>Total Seluruh Nilai Kekayaan"]
    J --> L["📋 Rincian Sumber Aset<br/>List Total itu dari Mana Saja"]
    J --> M["🔍 Detail Audit Saham<br/>Daftar Kepemilikan & Status ✅"]
```

---

### 💡 3 Poin Kunci untuk Dijelaskan ke Tim:

1. **Kenapa Tahap Spasial (Step 3) Sangat Penting?**
   Apple Vision membaca teks secara acak di layar dengan titik origin di kiri-bawah. Tahap spasial menginversi koordinat ke atas-bawah dan mengelompokkan teks yang sejajar ke dalam satu baris (`[Row 01]`). Ini mengunci hubungan antara nama saham, nominal modal, dan nilai pasar agar tidak tertukar.

2. **Kenapa Ada Jalur Cepat (Step 4)?**
   Untuk aplikasi yang sering dipakai (seperti Stockbit & Ajaib), sistem langsung mengenali polanya dalam **0,000 detik** tanpa membebani GPU/CPU dengan model AI. LLM hanya digunakan sebagai cadangan jika ada aplikasi baru.

3. **Kenapa Angka Lot Tidak Wajib (Step 5)?**
   Sistem menggunakan persamaan aljabar finansial:
   $$\text{Nilai Pasar} = \text{Modal (Invested)} + \text{Keuntungan/Kerugian (PnL)}$$
   Sehingga meskipun screenshot tidak menampilkan jumlah Lot, total nilai kekayaan tetap dapat dihitung dengan presisi 100%.
