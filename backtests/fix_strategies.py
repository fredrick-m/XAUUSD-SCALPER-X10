"""Fix broken f-string in all strategy __main__ blocks."""
import re
from pathlib import Path

strat_dir = Path(r"C:\Users\hp\XAUUSD-SCALPER-X10\strategies")
files = sorted(strat_dir.glob("strategy_s*.py"))
fixed = 0
for f in files:
    txt = f.read_text(encoding="utf-8")
    # The broken line looks like: print(f"Strategy "S001: EMA_3_8_Cross"")
    # Fix: use single-quoted outer string
    new_txt = re.sub(
        r'print\(f"Strategy "([^"]+)""\)',
        lambda m: 'print("Strategy ' + m.group(1) + '")',
        txt
    )
    if new_txt != txt:
        f.write_text(new_txt, encoding="utf-8")
        fixed += 1

print(f"Fixed {fixed} files")
