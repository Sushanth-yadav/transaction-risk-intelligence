from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent

DETAIL = ROOT / "apps" / "dashboard" / "templates" / "dashboard" / "detail.html"
JS = ROOT / "apps" / "dashboard" / "static" / "dashboard" / "js" / "investigation.js"

html = DETAIL.read_text(encoding="utf-8")

matches = re.findall(
    r"<script>(.*?)</script>",
    html,
    flags=re.IGNORECASE | re.DOTALL,
)

if not matches:
    raise SystemExit("No inline <script> blocks found in detail.html")

# The last inline script is the investigation assistant.
javascript = matches[-1].strip()

JS.write_text(javascript + "\n", encoding="utf-8")

print(f"JavaScript extracted to: {JS}")
print(f"JavaScript size: {len(javascript)} characters")