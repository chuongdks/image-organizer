import os
from pathlib import Path
from PIL import Image
import imagehash
from dataclasses import dataclass, field
from collections import defaultdict

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

@dataclass
class ImageRecord:
    path: str
    filename: str
    size_bytes: int
    width: int
    height: int
    phash: str
    duplicate_group: int | None = None  # filled in later
    tags: list[str] = field(default_factory=list)

def scan_folder(folder_path: str) -> list[ImageRecord]:
    """Scan a folder and return a list of ImageRecords."""
    records = []
    folder = Path(folder_path)

    if not folder.exists():
        raise ValueError(f"Folder not found: {folder_path}")

    for file in folder.rglob("*"):
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        try:
            with Image.open(file) as img:
                width, height = img.size
                phash = str(imagehash.phash(img))

            records.append(ImageRecord(
                path=str(file),
                filename=file.name,
                size_bytes=file.stat().st_size,
                width=width,
                height=height,
                phash=phash,
            ))
            print(f"  ✓ {file.name}")
        except Exception as e:
            print(f"  ✗ Skipping {file.name}: {e}")

    return records

def find_duplicates(records: list[ImageRecord], threshold: int = 8) -> list[ImageRecord]:
    """
    Group images with similar perceptual hashes.
    threshold: max hash distance to be considered a duplicate (0=identical, higher=more lenient)
    """
    groups = []          # list of lists of indices
    assigned = set()

    for i, rec_a in enumerate(records):
        if i in assigned:
            continue
        group = [i]
        hash_a = imagehash.hex_to_hash(rec_a.phash)

        for j, rec_b in enumerate(records):
            if j <= i or j in assigned:
                continue
            hash_b = imagehash.hex_to_hash(rec_b.phash)
            if hash_a - hash_b <= threshold:
                group.append(j)
                assigned.add(j)

        if len(group) > 1:
            assigned.add(i)
            groups.append(group)

    # Assign group IDs back to records
    for group_id, indices in enumerate(groups):
        for idx in indices:
            records[idx].duplicate_group = group_id

    return records