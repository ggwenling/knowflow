"""Rebuild with: python3 scripts/subset-heading-font.py /path/to/NotoSerifSC.ttf.

Only static display copy is styled with this face; user text keeps the UI face.
Requires fontTools[woff] (build-time only, no runtime package).
"""
from pathlib import Path
import re
import sys
from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

root = Path(__file__).resolve().parents[1]
copy = []
for path in sorted((root / "src").rglob("*.tsx")):
    text = path.read_text()
    copy.extend(re.findall(r"<h[12]\b[^>]*>(.*?)</h[12]>", text, re.S))
    copy.extend(re.findall(r'\btitle(?:=|:)\s*"([^"]+)"', text))
    copy.extend(re.findall(r'\btitle=\{(.*?)\}', text, re.S))
    copy.extend(re.findall(r'\btitle:\s*"([^"]+)"', text))
glyphs = "".join(sorted(set(re.findall(r"[\u3400-\u9fff]", "".join(copy)))))
glyphs += "0123456789，。！？：；、（）「」《》·…— /"
out = root / "src/app/fonts"
(out / "heading-glyphs.txt").write_text(glyphs + "\n")
font = TTFont(sys.argv[1])
options = subset.Options()
options.flavor = "woff2"
options.layout_features = ["*"]
subsetter = subset.Subsetter(options=options)
subsetter.populate(text=glyphs)
subsetter.subset(font)
font = instantiateVariableFont(font, {"wght": 400}, inplace=True)
font.recalcTimestamp = False
font.flavor = "woff2"
target = out / "noto-serif-sc-headings-400.woff2"
font.save(target)
print(f"{len(set(glyphs))} requested characters; {len(font.getBestCmap())} mapped glyphs; {target.stat().st_size} bytes")
