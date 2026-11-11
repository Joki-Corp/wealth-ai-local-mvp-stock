from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
PROCESSED_ASSETS_DIR = BASE_DIR / "processed_assets"
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_JSON_FILE = OUTPUT_DIR / "portfolio_result.json"

# Supported image file extensions
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}

# Stage 1: Gatekeeper thresholds
PHASH_CUTOFF = 2  # Hamming distance <= 2 is considered a duplicate
LONG_IMAGE_ASPECT_RATIO = 3.0  # height / width > 3.0 triggers vertical chunking
CHUNK_OVERLAP_RATIO = 0.15  # 15% vertical overlap between chunks

# Stage 2: OCR Settings (Apple Vision)
OCR_RECOGNITION_LEVEL = "accurate"
OCR_CONFIDENCE_THRESHOLD = 0.4

# Stage 3: Spatial coordinate clustering
Y_TOLERANCE = 0.015  # normalized y-axis tolerance for row clustering

# Stage 4: Local LLM Configuration (Ollama)
OLLAMA_MODEL = "qwen3.5:2b"
OLLAMA_TEMPERATURE = 0.0
OLLAMA_THINK = False  # Mandatory to disable think token generation

# Stage 5: Normalization & Math Validation
SHARES_PER_LOT = 100
MATH_TOLERANCE_PCT = 0.01  # 1% tolerance
MATH_TOLERANCE_NOMINAL = 5000.0  # Rp 5.000 max discrepancy

