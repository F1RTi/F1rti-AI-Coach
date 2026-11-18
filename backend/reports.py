import html
import json
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path

from .analytics import sessions, summarize
from .db import dump, now

LABELS = {
    "kd": "K/D",
    "kr": "K/R",
    "adr": "ADR",
    "hs": "Headshots, %",
    "winrate": "Победы, %",
    "kills": "Убийства",
    "deaths": "Смерти",
    "assists": "Помощь",
    "mvp": "MVP",
    "variability": "Разброс ADR",
}


def report(store, kind, ref=None, games=None, group=None):
    games = store.matches() if games is None else games
    if not games:
        raise ValueError("Для отчёта требуется хотя бы один матч")
    if kind == "Матч":
        selected = [
            next((g for g in games if g["id"] == (ref or games[0]["id"])), None)
        ]
        if not selected[0]:
            raise ValueError("Матч не найден")
        key = selected[0]["id"]
    elif kind == "Сессия":
        if group is None:
            groups = sessions(games, store.settings()["session_gap"])
            group = next((g for g in groups if not ref or g["id"] == ref), None)
        if not group:
            raise ValueError("Нет сессии с известным временем")
        key = group["id"]
        ids = set(group["matches"])
        selected = [m for m in games if m["id"] in ids]
    else:
        days = {"Неделя": 7, "Месяц": 30}[kind]
        selected = [g for g in games if (g["finished"] or 0) >= now() - days * 86400]
        if not selected:
            raise ValueError("За этот период нет матчей")
        key = datetime.now().date().isoformat()
    key = kind + "-" + key
    data = dict(
        kind=kind,
        matches=[m["id"] for m in selected],
        metrics=summarize(selected),
        complete=all(m["complete"] for m in selected),
        start=min((m["finished"] for m in selected if m["finished"]), default=None),
        end=max((m["finished"] for m in selected if m["finished"]), default=None),
    )
    with store.connect() as db:
        db.execute(
            "INSERT OR REPLACE INTO reports VALUES(?,?,?,?)",
            (key, kind + " · F1rti", now(), dump(data)),
        )
    return key


def markup(row):
    esc = lambda v: html.escape(str(v), quote=True)
    d = json.loads(row["data"])
    cells = "".join(
        f"<tr><th>{esc(label)}</th><td>{esc(m['value']) if m['available'] else '—'}</td><td>{esc(m['method'])}</td><td>{m['sample']}</td></tr>"
        for k, label in LABELS.items()
        for m in [d["metrics"][k]]
    )
    ids = "".join("<li>" + esc(mid) + "</li>" for mid in d["matches"])
    stamp = datetime.fromtimestamp(row["at"]).strftime("%d.%m.%Y %H:%M")
    return f"""<!doctype html><html lang="ru"><meta charset="utf-8"><title>{esc(row["title"])}</title>
<style>@page{{margin:18mm}}body{{font:15px Segoe UI,sans-serif;max-width:900px;margin:36px auto;color:#1e2328}}header{{border-top:6px solid #f16a26}}h1{{font-size:38px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:9px;border-bottom:1px solid #ccc}}tr{{break-inside:avoid}}small{{color:#555}}</style>
<header><p>F1RTI / AI COACH</p><h1>{esc(row["title"])}</h1></header><p>{stamp} · Источник FACEIT · Матчей {len(d["matches"])}</p>
<table><thead><tr><th>Метрика</th><th>Значение</th><th>Расчёт</th><th>Выборка</th></tr></thead>{cells}</table><h2>Матчи в отчёте</h2><ul>{ids}</ul></html>"""


def browser():
    for root in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        for rel in (
            "Microsoft/Edge/Application/msedge.exe",
            "Google/Chrome/Application/chrome.exe",
        ):
            p = Path(os.environ.get(root, ".")) / rel
            if p.is_file():
                return str(p)
    return None


def pdf(row):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    fonts = Path(os.environ["WINDIR"]) / "Fonts"
    for name, file in (("Coach", "arial.ttf"), ("CoachBold", "arialbd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=row["title"],
        author="F1rti AI Coach",
        leftMargin=42,
        rightMargin=42,
        topMargin=52,
        bottomMargin=42,
    )
    d = json.loads(row["data"])

    def paragraph(text, size=10, bold=False):
        style = ParagraphStyle(
            "text",
            fontName="CoachBold" if bold else "Coach",
            fontSize=size,
            leading=size * 1.5,
        )
        return Paragraph(html.escape(str(text)), style)

    stamp = datetime.fromtimestamp(row["at"]).strftime("%d.%m.%Y %H:%M")
    story = [
        paragraph("F1RTI  /  AI COACH", 10, True),
        Spacer(1, 12),
        paragraph(row["title"], 24, True),
        paragraph(f"{stamp}  ·  FACEIT  ·  Матчей {len(d['matches'])}"),
        Spacer(1, 20),
    ]
    rows = [["Показатель", "Значение", "Метод", "Выборка"]]
    for k, label in LABELS.items():
        m = d["metrics"][k]
        rows.append(
            [
                label,
                str(m["value"]) if m["available"] else "—",
                m["method"],
                str(m["sample"]),
            ]
        )
    cells = [
        [paragraph(text, 9, i == 0) for text in values] for i, values in enumerate(rows)
    ]
    table = Table(cells, colWidths=[100, 66, 266, 62], repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5e9de")),
                ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    story.extend([table, Spacer(1, 18), paragraph("Матчи в отчёте", 14, True)])
    story.extend(paragraph(mid, 9) for mid in d["matches"])

    def footer(canvas, document):
        canvas.setFillColor(colors.HexColor("#f27630"))
        canvas.rect(42, A4[1] - 34, A4[0] - 84, 3, fill=1, stroke=0)
        canvas.setFont("Coach", 9)
        canvas.setFillColor(colors.grey)
        canvas.drawRightString(A4[0] - 42, 23, str(document.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
