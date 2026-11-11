import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
from PIL import Image
import imagehash

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pass

from src.config import (
    ASSETS_DIR,
    PROCESSED_ASSETS_DIR,
    SUPPORTED_EXTENSIONS,
    PHASH_CUTOFF,
    LONG_IMAGE_ASPECT_RATIO,
    CHUNK_OVERLAP_RATIO,
)
from src.logger import StageLogger


@dataclass
class ProcessedImageInfo:
    """Metadata for an image processed for OCR."""
    processed_path: Path
    original_filename: str
    is_chunk: bool = False
    chunk_index: int = 0


def compute_md5(file_path: Path) -> str:
    """Compute MD5 hash of raw file bytes."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def convert_to_rgb(img: Image.Image) -> Image.Image:
    """Safely convert PIL Image to RGB mode, flattening transparency on white."""
    if img.mode == "RGB":
        return img
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        alpha = img.convert("RGBA")
        background = Image.new("RGBA", alpha.size, (255, 255, 255, 255))
        alpha_composite = Image.alpha_composite(background, alpha)
        return alpha_composite.convert("RGB")
    return img.convert("RGB")


def process_gatekeeper(
    assets_dir: Path = ASSETS_DIR,
    processed_dir: Path = PROCESSED_ASSETS_DIR,
    logger: StageLogger = None,
) -> List[ProcessedImageInfo]:
    """
    Stage 1: Scan assets, filter exact and visual duplicates, convert to RGB PNG,
    and slice long scrolling screenshots into chunks.
    """
    processed_dir.mkdir(parents=True, exist_ok=True)

    # 1. Scan directory
    raw_files = [
        f for f in sorted(assets_dir.iterdir())
        if not f.name.startswith(".") and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    if logger:
        logger.log(f"Loaded {len(raw_files)} files from {assets_dir}")

    if not raw_files:
        return []

    seen_md5 = set()
    seen_phashes: List[Tuple[imagehash.ImageHash, str]] = []
    processed_images: List[ProcessedImageInfo] = []

    dropped_count = 0
    converted_count = 0

    for file_path in raw_files:
        # 2. Exact Deduplication (MD5)
        file_md5 = compute_md5(file_path)
        if file_md5 in seen_md5:
            dropped_count += 1
            if logger:
                logger.log(f"Dropped duplicate image ({file_path.name} via MD5 match)")
            continue
        seen_md5.add(file_md5)

        # Open image
        try:
            with Image.open(file_path) as raw_img:
                rgb_img = convert_to_rgb(raw_img)

                # 3. Visual Deduplication (pHash)
                current_phash = imagehash.phash(rgb_img)
                is_duplicate = False
                for prev_phash, prev_name in seen_phashes:
                    dist = current_phash - prev_phash
                    if dist <= PHASH_CUTOFF:
                        is_duplicate = True
                        dropped_count += 1
                        if logger:
                            logger.log(f"Dropped duplicate image ({file_path.name} via pHash dist={dist} from {prev_name})")
                        break

                if is_duplicate:
                    continue

                seen_phashes.append((current_phash, file_path.name))

                # 4 & 5. Standardization and Long-Screenshot Chunking
                w, h = rgb_img.size
                aspect_ratio = h / w if w > 0 else 0

                if aspect_ratio > LONG_IMAGE_ASPECT_RATIO:
                    # Scrolling screenshot detected: slice into overlapping chunks
                    chunk_height = int(w * 2.5)
                    step = int(chunk_height * (1.0 - CHUNK_OVERLAP_RATIO))
                    y_start = 0
                    chunk_idx = 1
                    created_chunks = 0

                    while y_start < h:
                        y_end = min(y_start + chunk_height, h)
                        chunk_img = rgb_img.crop((0, y_start, w, y_end))

                        chunk_name = f"{file_path.stem}_chunk_{chunk_idx:02d}.png"
                        chunk_path = processed_dir / chunk_name
                        chunk_img.save(chunk_path, "PNG")

                        processed_images.append(
                            ProcessedImageInfo(
                                processed_path=chunk_path,
                                original_filename=file_path.name,
                                is_chunk=True,
                                chunk_index=chunk_idx,
                            )
                        )
                        created_chunks += 1
                        chunk_idx += 1
                        if y_end >= h:
                            break
                        y_start += step

                    converted_count += 1
                    if logger:
                        logger.log(f"Sliced scrolling screenshot {file_path.name} (aspect {aspect_ratio:.1f}) into {created_chunks} chunks")
                else:
                    # Standard aspect ratio
                    out_name = f"{file_path.stem}.png"
                    out_path = processed_dir / out_name
                    rgb_img.save(out_path, "PNG")

                    processed_images.append(
                        ProcessedImageInfo(
                            processed_path=out_path,
                            original_filename=file_path.name,
                            is_chunk=False,
                            chunk_index=0,
                        )
                    )
                    converted_count += 1

        except Exception as e:
            if logger:
                logger.log(f"[bold red]Failed to process {file_path.name}:[/bold red] {e}")

    if logger:
        logger.log(f"Converted {converted_count} unique image(s) to RGB PNG in {processed_dir.name}")

    return processed_images

