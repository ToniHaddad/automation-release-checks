"""Run pprc on the noncompliant sample and write docs/terminal.html (for the README image)."""
import html
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
cmd = ["check", "samples/noncompliant", "--manifest", "governance.yml",
       "--rules", "rules.yml", "--today", "2026-11-20"]
out = subprocess.run([sys.executable, "-m", "pprc", *cmd], cwd=root,
                     capture_output=True, text=True, encoding="utf-8").stdout
(root / "docs" / "sample-output.txt").write_text(out, encoding="utf-8")

body = []
for line in out.splitlines():
    e = html.escape(line)
    if line.startswith("PPRC"):
        rule, _, loc = e.partition("  ")
        e = f'<span class="rule">{rule}</span>  <span class="loc">{loc}</span>'
    elif line.strip().startswith("Fix:"):
        e = e.replace("Fix:", '<span class="fix">Fix:</span>', 1)
    elif line.startswith("FAILED"):
        e = f'<span class="fail">{e}</span>'
    body.append(e)

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>pprc output</title>
<style>
body {{ margin:0; background:#0f1419; padding:24px; }}
.term {{ max-width:1080px; margin:0 auto; background:#161c24; border:1px solid #2a3340; border-radius:10px; overflow:hidden; }}
.bar {{ background:#1d2530; padding:10px 14px; color:#8b98a8; font:13px system-ui,sans-serif; }}
.bar i {{ display:inline-block; width:11px; height:11px; border-radius:50%; margin-right:6px; background:#3a4656; }}
pre {{ margin:0; padding:18px 20px; color:#d5dde8; font:14px/1.55 Consolas,"DejaVu Sans Mono",monospace; white-space:pre-wrap; }}
.prompt {{ color:#7fd1a6; }} .rule {{ color:#ff7b72; font-weight:bold; }} .loc {{ color:#79c0ff; }}
.fix {{ color:#e3b341; }} .fail {{ color:#ff7b72; font-weight:bold; }}
</style></head><body>
<div class="term"><div class="bar"><i></i><i></i><i></i> pprc check</div>
<pre><span class="prompt">$</span> pprc check samples/noncompliant --manifest governance.yml --rules rules.yml
{chr(10).join(body)}
<span class="prompt">$</span> echo $?
1</pre></div></body></html>
"""
(root / "docs" / "terminal.html").write_text(page, encoding="utf-8")
print("written")
