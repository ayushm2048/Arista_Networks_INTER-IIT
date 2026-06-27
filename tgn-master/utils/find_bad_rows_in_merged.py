# utils/find_bad_rows_in_merged.py
import sys
from pathlib import Path

def find_bad_rows(merged_path: Path, show=10, write_clean=False):
    if not merged_path.exists():
        print("Merged CSV not found:", merged_path)
        return 1

    with merged_path.open("r", encoding="utf-8", errors="replace") as f:
        header = f.readline().rstrip("\n")
        expected_fields = header.count(",") + 1
        expected_commas = expected_fields - 1
        print(f"Header fields = {expected_fields} (commas={expected_commas})")
        bad = []
        # iterate and collect bad lines
        for i, line in enumerate(f, start=2):
            # count commas; simple check
            if line.count(",") != expected_commas:
                bad.append((i, line.rstrip("\n")))
                if len(bad) >= show:
                    break

    if not bad:
        print("No bad rows found (first scan).")
        return 0

    print(f"Found {len(bad)} bad rows (showing up to {show}):")
    for ln, content in bad:
        print(f" LINE {ln}: commas={content.count(',')}  preview: {content[:300]!r}")

    if write_clean:
        out_clean = merged_path.with_name(merged_path.stem + "_clean.csv")
        print("Writing cleaned file (skipping bad lines) →", out_clean)
        with merged_path.open("r", encoding="utf-8", errors="replace") as inf, out_clean.open("w", encoding="utf-8") as outf:
            header = inf.readline()
            outf.write(header)
            for i, line in enumerate(inf, start=2):
                if line.count(",") == expected_commas:
                    outf.write(line)
        print("Done. Clean file written.")
    return 0

if __name__ == "__main__":
    p = Path("data/ml_mywifi.csv")
    write_clean = "--write-clean" in sys.argv
    show = 20
    sys.exit(find_bad_rows(p, show=show, write_clean=write_clean))
