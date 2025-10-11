# remove_trailing_brace.py
from pathlib import Path

src = Path("mmx-cli/src/main.rs")
lines = src.read_text().splitlines()
if len(lines) >= 56 and lines[55].strip() == "}":
    lines.pop(55)
    src.write_text("\n".join(lines) + "\n")
    print("[ok] Removed stray closing brace at line 56.")
else:
    print("[skip] No lone '}' at line 56 to remove.")
