from pipeline.ingestor import scan_folder, find_duplicates
from collections import defaultdict
import json

if __name__ == "__main__":
    folder = input("Enter folder path: ").strip()

    print("\n📂 Scanning folder...")
    records = scan_folder(folder)
    print(f"\n✅ Found {len(records)} images")

    print("\n🔍 Detecting duplicates...")
    records = find_duplicates(records)

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