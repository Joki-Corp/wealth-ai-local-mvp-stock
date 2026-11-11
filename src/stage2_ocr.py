import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
from src.config import OCR_RECOGNITION_LEVEL, OCR_CONFIDENCE_THRESHOLD
from src.logger import StageLogger
from src.stage1_gatekeeper import ProcessedImageInfo


@dataclass
class OCRItem:
    """Single OCR detected text element with normalized coordinates."""
    text: str
    confidence: float
    bbox: List[float]  # [x, y, w, h] in normalized Vision coordinates


@dataclass
class ImageOCRResult:
    """OCR output for one processed image."""
    image_info: ProcessedImageInfo
    items: List[OCRItem]


def run_ocr_on_image(image_path: Path, confidence_threshold: float = OCR_CONFIDENCE_THRESHOLD) -> List[OCRItem]:
    """
    Run native Apple Vision OCR via ocrmac on a single image file.
    Filters out results with confidence below the threshold.
    """
    try:
        from ocrmac import ocrmac
        raw_results = ocrmac.OCR(str(image_path), recognition_level=OCR_RECOGNITION_LEVEL).recognize()
    except ImportError:
        raise ImportError(
            "The 'ocrmac' package is required on macOS. Please run 'pip install ocrmac'."
        )
    except Exception as e:
        raise RuntimeError(f"Apple Vision OCR execution failed on {image_path.name}: {e}")

    filtered_items: List[OCRItem] = []
    for item in raw_results:
        # ocrmac returns tuples: (text, confidence, [x, y, w, h])
        if len(item) == 3:
            text, conf, bbox = item
            clean_text = str(text).strip()
            if clean_text and conf >= confidence_threshold:
                filtered_items.append(OCRItem(text=clean_text, confidence=conf, bbox=list(bbox)))

    return filtered_items


def process_ocr(
    images: List[ProcessedImageInfo],
    logger: StageLogger = None,
) -> List[ImageOCRResult]:
    """
    Stage 2: Run ocrmac Apple Vision OCR across all prepared images.
    """
    results: List[ImageOCRResult] = []

    for img_info in images:
        t0 = time.perf_counter()
        ocr_items = run_ocr_on_image(img_info.processed_path)
        duration = time.perf_counter() - t0

        results.append(ImageOCRResult(image_info=img_info, items=ocr_items))

        if logger:
            logger.log(
                f"{img_info.processed_path.name}: Extracted {len(ocr_items)} text boxes ({duration:.3f}s)"
            )

    return results

