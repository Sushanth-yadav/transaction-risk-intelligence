from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent

BASE = ROOT / "apps" / "dashboard" / "templates" / "dashboard" / "base.html"
CSS = ROOT / "apps" / "dashboard" / "static" / "dashboard" / "css" / "dashboard.css"

html = BASE.read_text(encoding="utf-8")

match = re.search(
    r"<style[^>]*>(.*?)</style>",
    html,
    flags=re.IGNORECASE | re.DOTALL,
)

if not match:
    raise SystemExit("No <style>...</style> block found in base.html")

css = match.group(1).strip()

CSS.write_text(css + "\n", encoding="utf-8")

print(f"CSS extracted to: {CSS}")
print(f"CSS size: {len(css)} characters")