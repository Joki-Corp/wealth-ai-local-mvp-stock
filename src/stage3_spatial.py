from dataclasses import dataclass
from typing import List
from src.config import Y_TOLERANCE
from src.logger import StageLogger
from src.stage1_gatekeeper import ProcessedImageInfo
from src.stage2_ocr import OCRItem, ImageOCRResult


@dataclass
class SpatialElement:
    """Wrapper for OCRItem with converted top-down coordinates."""
    ocr_item: OCRItem
    x: float
    y_center: float


@dataclass
class SpatialFormattedResult:
    """Formatted spatial representation of OCR results for LLM consumption."""
    image_info: ProcessedImageInfo
    spatial_text: str
    total_rows: int


def cluster_into_spatial_rows(
    items: List[OCRItem],
    y_tolerance: float = Y_TOLERANCE,
) -> List[List[OCRItem]]:
    """
    Groups OCR bounding boxes into horizontal rows using vertical tolerance.
    Inverts Apple Vision's bottom-left origin so row 1 is at the top of the image.
    Within each row, items are sorted from left to right (x ascending).
    """
    if not items:
        return []

    # Invert y to standard top-down coordinates:
    # Apple Vision: (0,0) is bottom-left, box is [x, y, w, h]
    # top_down_y_center = 1.0 - (y + h / 2.0)
    spatial_elements: List[SpatialElement] = []
    for it in items:
        x, y, w, h = it.bbox
        y_center = 1.0 - (y + (h / 2.0))
        spatial_elements.append(SpatialElement(ocr_item=it, x=x, y_center=y_center))

    # Sort primarily by top-down vertical position
    spatial_elements.sort(key=lambda elem: elem.y_center)

    rows: List[List[SpatialElement]] = []
    current_row: List[SpatialElement] = []
    current_row_y_center: float = 0.0

    for elem in spatial_elements:
        if not current_row:
            current_row.append(elem)
            current_row_y_center = elem.y_center
        else:
            # Check if within tolerance of current row's center
            if abs(elem.y_center - current_row_y_center) <= y_tolerance:
                current_row.append(elem)
                # Recalculate running center
                current_row_y_center = sum(e.y_center for e in current_row) / len(current_row)
            else:
                rows.append(current_row)
                current_row = [elem]
                current_row_y_center = elem.y_center

    if current_row:
        rows.append(current_row)

    # Sort each row left-to-right (x ascending) and unwrap to OCRItem
    sorted_rows: List[List[OCRItem]] = []
    for row in rows:
        row.sort(key=lambda elem: elem.x)
        sorted_rows.append([elem.ocr_item for elem in row])

    return sorted_rows


def format_spatial_text(rows: List[List[OCRItem]]) -> str:
    """
    Render clustered rows into structured line format:
    [Row 01] Item 1 | Item 2 | Item 3
    [Row 02] Item 4 | Item 5
    """
    lines: List[str] = []
    for idx, row in enumerate(rows, start=1):
        line_content = " | ".join(item.text for item in row)
        lines.append(f"[Row {idx:02d}] {line_content}")
    return "\n".join(lines)


def process_spatial(
    ocr_results: List[ImageOCRResult],
    y_tolerance: float = Y_TOLERANCE,
    logger: StageLogger = None,
) -> List[SpatialFormattedResult]:
    """
    Stage 3: Transform raw OCR coordinate tuples into ordered spatial text.
    """
    spatial_results: List[SpatialFormattedResult] = []

    for ocr_res in ocr_results:
        rows = cluster_into_spatial_rows(ocr_res.items, y_tolerance=y_tolerance)
        spatial_text = format_spatial_text(rows)

        spatial_results.append(
            SpatialFormattedResult(
                image_info=ocr_res.image_info,
                spatial_text=spatial_text,
                total_rows=len(rows),
            )
        )

        if logger:
            logger.log(
                f"{ocr_res.image_info.processed_path.name}: Grouped into {len(rows)} spatial rows"
            )

    return spatial_results

