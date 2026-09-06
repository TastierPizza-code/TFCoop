"""Render the small, local Markdown guide without browser automation."""
from pathlib import Path
import html
import re

ROOT = Path(__file__).resolve().parents[1]


def inline(value):
    text = html.escape(value)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\[([^\]]+)\]\((https://[^)]+)\)", r'<a href="\2">\1</a>', text)
    return text


def render(markdown):
    lines = markdown.splitlines()
    blocks, paragraph, items, list_kind, table = [], [], [], None, []
    def flush():
        nonlocal list_kind
        if paragraph:
            blocks.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()
        if items:
            blocks.append("<" + list_kind + ">" + "".join("<li>" + inline(item) + "</li>" for item in items) + "</" + list_kind + ">")
            items.clear()
        list_kind = None
        if table:
            rows = []
            for index, row in enumerate(table):
                tag = "th" if index == 0 else "td"
                rows.append("<tr>" + "".join(f"<{tag}>" + inline(cell.strip()) + f"</{tag}>" for cell in row) + "</tr>")
            blocks.append("<div class=table><table>" + "".join(rows) + "</table></div>")
            table.clear()
    for line in lines:
        if not line.strip():
            flush()
        elif line.startswith("#"):
            flush()
            heading, content = line.split(" ", 1)
            blocks.append(f"<h{len(heading)}>" + inline(content) + f"</h{len(heading)}>")
        elif line.startswith("|"):
            if not re.fullmatch(r"[|\s:-]+", line):
                table.append(line.strip("|").split("|"))
        elif re.match(r"^\d+\. |^- ", line):
            kind = "ol" if line[0].isdigit() else "ul"
            if paragraph or list_kind and kind != list_kind:
                flush()
            list_kind = kind
            items.append(re.sub(r"^(\d+\. |\- )", "", line))
        elif line.startswith("  ") and items:
            items[-1] += " " + line.strip()
        else:
            if items or table:
                flush()
            paragraph.append(line.strip())
    flush()
    return """<!doctype html><html lang="de"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TF2-Koop Alpha5.4-Diagnose · Anleitung</title>
<style>
body{margin:0;background:#eef2f6;color:#202c3c;font:17px/1.6 system-ui,Segoe UI,sans-serif}
main{max-width:940px;margin:32px auto;padding:38px 46px;background:white;border-radius:12px}
h1{font-size:32px;line-height:1.25;color:#163c69;margin-top:0}h2{font-size:24px;line-height:1.35;margin-top:38px;border-top:1px solid #dde5ef;padding-top:23px}
li{padding-left:5px;margin:9px 0}code{font:0.88em Consolas,monospace;background:#edf2f8;padding:2px 5px;overflow-wrap:anywhere}
a{color:#145ea5}strong{font-weight:650}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:15px}
th,td{border:1px solid #d7e0ea;padding:12px;text-align:left;vertical-align:top}th{background:#edf2f8}
@media(max-width:700px){main{margin:0;border-radius:0;padding:22px;font-size:16px}h1{font-size:27px}}
@media print{body{background:white}main{margin:0;padding:0;max-width:none}h2{break-after:avoid}li,tr{break-inside:avoid}}
</style><main>""" + "\n".join(blocks) + "</main></html>"


if __name__ == "__main__":
    source = ROOT / "prototype/ANLEITUNG.md"
    target = source.with_suffix(".html")
    target.write_text(render(source.read_text("utf-8")), encoding="utf-8")
    print(target)
