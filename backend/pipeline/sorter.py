import shutil
from pathlib import Path
from backend.pipeline.ingestor import ImageRecord
from backend.pipeline.tagger import ImageTags

def sort_images(records: list[ImageRecord], tags: list[ImageTags], 
                output_folder: str) -> None:
    output = Path(output_folder)

    for record, tag in zip(records, tags):
        # Determine destination folder
        if tag.failed:
            folder = output / "failed"
        elif tag.is_nsfw:
            folder = output / "nsfw"
        elif record.duplicate_group is not None:
            folder = output / "duplicates" / f"group_{record.duplicate_group}"
        else:
            folder = output / tag.category

        folder.mkdir(parents=True, exist_ok=True)

        # Copy the image
        dest = folder / record.filename
        # Handle filename conflicts (two different folders might have same filename)
        if dest.exists():
            dest = folder / f"{Path(record.filename).stem}_1{Path(record.filename).suffix}"
        shutil.copy2(record.path, dest)

        # Write sidecar .txt with full tag info
        sidecar = dest.with_suffix(".txt")
        sidecar.write_text(
            f"Original path : {record.path}\n"
            f"Category      : {tag.category}\n"
            f"Tags          : {', '.join(tag.tags)}\n"
            f"NSFW          : {tag.is_nsfw}\n"
            f"OCR text      : {tag.ocr_text}\n"
            f"Description   : {tag.description}\n"
            f"Backend       : {tag.backend}\n"
        )
        print(f"  → {record.filename} copied to {folder.name}/")