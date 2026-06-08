from backend.pipeline.ingestor import scan_folder, find_duplicates
from backend.pipeline.tagger import tag_with_ollama, tag_with_claude
from collections import defaultdict
from backend.pipeline.sorter import sort_images
import json, os

BACKEND = "ollama"           # switch to "claude" to use Haiku
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

if __name__ == "__main__":
    folder = input("Enter folder path: ").strip()
    output = input("Enter output folder path: ").strip()

    print("\n📂 Scanning folder...")
    records = scan_folder(folder)
    print(f"\n✅ Found {len(records)} images")

    print("\n🔍 Detecting duplicates...")
    records = find_duplicates(records)
    
    print(f"\n🤖 Tagging with {BACKEND}...")
    all_tags = []
    for rec in records:
        print(f"  → {rec.filename}")
        if BACKEND == "ollama":
            tags = tag_with_ollama(rec.path)
        else:
            tags = tag_with_claude(rec.path, CLAUDE_API_KEY)
        all_tags.append(tags)

        # Print result
        print(f"     category : {tags.category}")
        print(f"     tags     : {tags.tags}")
        print(f"     nsfw     : {tags.is_nsfw}")
        print(f"     text     : {tags.ocr_text[:60] if tags.ocr_text else '-'}")
        print(f"     desc     : {tags.description}")
        print()
        
    print(f"\n📁 Sorting into {output}...")
    sort_images(records, all_tags, output)
        
    # Summary
    dup_groups = defaultdict(list)
    for r in records:
        if r.duplicate_group is not None:
            dup_groups[r.duplicate_group].append(r.filename)

    print(f"\n📊 Results:")
    print(f"  Total images : {len(records)}")
    print(f"  Duplicate groups: {len(dup_groups)}")

    for group_id, filenames in dup_groups.items():
        print(f"\n  Group {group_id + 1}:")
        for name in filenames:
            print(f"    - {name}")
    
    print("\n✅ Done!")