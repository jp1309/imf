#!/usr/bin/env python3
"""Genera el PDF y los PNG del proyecto desde forecasts.json."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas

from scripts.validate_data import validate_repository


NAVY = "#0b253a"
SLATE = "#66788a"
GRID = "#dfe6ec"
ACTUAL = "#071b2a"
BG = "#f5f8fa"
TEAL = "#0d9488"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def variable_meta(data: dict, variable: str) -> dict:
    return data["meta"]["variables"][variable]


def format_number(value: float | None, decimals: int) -> str:
    if value is None or not math.isfinite(value):
        return "-"
    return f"{value:,.{decimals}f}"


def calculate_metrics(data: dict, variable: str) -> list[dict]:
    actual = {int(year): value for year, value in data["actual"][variable].items()}
    metrics = []
    for name, vintage in data["vintages"].items():
        forecast = {int(year): value for year, value in vintage["data"][variable].items()}
        errors = [forecast[year] - actual[year] for year in sorted(set(actual) & set(forecast))]
        metrics.append(
            {
                "name": name,
                "color": vintage["color"],
                "n": len(errors),
                "mae": statistics.fmean(abs(value) for value in errors) if errors else None,
                "rmse": math.sqrt(statistics.fmean(value * value for value in errors)) if errors else None,
                "bias": statistics.fmean(errors) if errors else None,
            }
        )
    return metrics


def chart_series(data: dict, variable: str) -> tuple[list[int], list[dict]]:
    actual = {int(year): value for year, value in data["actual"][variable].items()}
    years = set(actual)
    for vintage in data["vintages"].values():
        years.update(int(year) for year in vintage["data"][variable])
    sorted_years = sorted(years)
    series = [{"name": "Histórico / estimado", "color": ACTUAL, "values": actual, "actual": True}]
    for name, vintage in data["vintages"].items():
        values = {int(year): value for year, value in vintage["data"][variable].items()}
        connect_year = int(vintage["projStart"]) - 1
        if connect_year in actual:
            values = {connect_year: actual[connect_year], **values}
        series.append({"name": name, "color": vintage["color"], "values": values, "actual": False})
    return sorted_years, series


def scale_bounds(series: list[dict]) -> tuple[float, float]:
    values = [value for item in series for value in item["values"].values() if math.isfinite(value)]
    low, high = min(values), max(values)
    if math.isclose(low, high):
        return low - 1, high + 1
    padding = (high - low) * 0.1
    return low - padding, high + padding


def map_point(year: int, value: float, years: list[int], low: float, high: float, x: float, y: float, w: float, h: float) -> tuple[float, float]:
    px = x + (year - years[0]) / max(1, years[-1] - years[0]) * w
    py = y + (value - low) / max(1e-9, high - low) * h
    return px, py


def pdf_color(hex_color: str):
    return colors.HexColor(hex_color)


def draw_pdf_chart(c: canvas.Canvas, data: dict, variable: str, x: float, y: float, w: float, h: float) -> None:
    years, series = chart_series(data, variable)
    low, high = scale_bounds(series)
    plot_x, plot_y, plot_w, plot_h = x + 46, y + 34, w - 62, h - 54

    c.setFillColor(pdf_color("#ffffff"))
    c.roundRect(x, y, w, h, 9, fill=1, stroke=0)
    c.setStrokeColor(pdf_color(GRID))
    c.setLineWidth(0.6)
    for step in range(6):
        value = low + (high - low) * step / 5
        py = plot_y + plot_h * step / 5
        c.line(plot_x, py, plot_x + plot_w, py)
        c.setFillColor(pdf_color(SLATE))
        c.setFont("Helvetica", 7)
        c.drawRightString(plot_x - 6, py - 2, format_number(value, 1))

    for year in years:
        px, _ = map_point(year, low, years, low, high, plot_x, plot_y, plot_w, plot_h)
        c.setFillColor(pdf_color(SLATE))
        c.setFont("Helvetica", 7)
        c.saveState()
        c.translate(px, plot_y - 8)
        c.rotate(45)
        c.drawRightString(0, 0, str(year))
        c.restoreState()

    last_actual = int(data["meta"]["actualThrough"])
    if last_actual < years[-1]:
        zone_x, _ = map_point(last_actual, low, years, low, high, plot_x, plot_y, plot_w, plot_h)
        c.setFillColor(pdf_color("#eaf3f8"))
        c.rect(zone_x, plot_y, plot_x + plot_w - zone_x, plot_h, fill=1, stroke=0)
        c.setStrokeColor(pdf_color("#758899"))
        c.setDash(3, 3)
        c.line(zone_x, plot_y, zone_x, plot_y + plot_h)
        c.setDash()

    for item in series:
        points = []
        for year in years:
            if year in item["values"]:
                points.append(map_point(year, item["values"][year], years, low, high, plot_x, plot_y, plot_w, plot_h))
            elif len(points) > 1:
                draw_pdf_polyline(c, points, item)
                points = []
        if len(points) > 1:
            draw_pdf_polyline(c, points, item)

    legend_x = x + 12
    legend_y = y + h - 14
    c.setFont("Helvetica", 6.8)
    for index, item in enumerate(series):
        col = index % 4
        row = index // 4
        lx = legend_x + col * (w - 24) / 4
        ly = legend_y - row * 12
        c.setStrokeColor(pdf_color(item["color"]))
        c.setLineWidth(2 if item["actual"] else 1.2)
        if not item["actual"]:
            c.setDash(4, 3)
        c.line(lx, ly, lx + 17, ly)
        c.setDash()
        c.setFillColor(pdf_color(SLATE))
        c.drawString(lx + 21, ly - 2, item["name"])


def draw_pdf_polyline(c: canvas.Canvas, points: list[tuple[float, float]], item: dict) -> None:
    c.setStrokeColor(pdf_color(item["color"]))
    c.setFillColor(pdf_color(item["color"]))
    c.setLineWidth(2.5 if item["actual"] else 1.4)
    if not item["actual"]:
        c.setDash(5, 3)
    path = c.beginPath()
    path.moveTo(*points[0])
    for point in points[1:]:
        path.lineTo(*point)
    c.drawPath(path, fill=0, stroke=1)
    c.setDash()
    radius = 2.1 if item["actual"] else 1.25
    for px, py in points:
        c.circle(px, py, radius, fill=1, stroke=0)


def draw_pdf_metrics(c: canvas.Canvas, data: dict, variable: str, x: float, y: float, w: float) -> None:
    meta = variable_meta(data, variable)
    metrics = calculate_metrics(data, variable)
    headers = ["Vintage", "N", f"MAE ({meta['unit']})", "RMSE", "Sesgo"]
    widths = [w * 0.34, w * 0.1, w * 0.19, w * 0.19, w * 0.18]
    row_h = 17

    c.setFillColor(pdf_color(NAVY))
    c.roundRect(x, y + row_h * len(metrics), w, row_h, 4, fill=1, stroke=0)
    cursor = x
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 8)
    for header, width in zip(headers, widths):
        c.drawString(cursor + 6, y + row_h * len(metrics) + 5, header)
        cursor += width

    for index, metric in enumerate(metrics):
        row_y = y + row_h * (len(metrics) - index - 1)
        c.setFillColor(pdf_color("#f5f8fa" if index % 2 else "#ffffff"))
        c.rect(x, row_y, w, row_h, fill=1, stroke=0)
        values = [
            metric["name"],
            str(metric["n"]),
            format_number(metric["mae"], meta["decimals"]),
            format_number(metric["rmse"], meta["decimals"]),
            format_number(metric["bias"], meta["decimals"]),
        ]
        cursor = x
        c.setFont("Helvetica", 7.5)
        for column, (value, width) in enumerate(zip(values, widths)):
            c.setFillColor(pdf_color(metric["color"] if column == 0 else "#3f5264"))
            c.drawString(cursor + 6, row_y + 5, value)
            cursor += width


def build_pdf(root: Path, data: dict, manifest: dict) -> Path:
    output = root / "IMF_Ecuador_Vintages.pdf"
    page_w, page_h = landscape(A4)
    c = canvas.Canvas(str(output), pagesize=(page_w, page_h))
    c.setTitle("Ecuador - Pronósticos del FMI frente a la historia revisada")
    c.setAuthor("Juan Pablo")
    c.setSubject("Comparación reproducible de vintages macroeconómicos del FMI")

    c.setFillColor(pdf_color(NAVY))
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    c.setFillColor(pdf_color("#69d0c4"))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(48, page_h - 62, "ECUADOR | IMF FORECAST MONITOR")
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 29)
    c.drawString(48, page_h - 112, "Pronósticos del FMI frente")
    c.drawString(48, page_h - 148, "a la historia revisada")
    c.setFillColor(pdf_color("#d6e6ef"))
    c.setFont("Helvetica", 13)
    c.drawString(48, page_h - 184, "Ocho variables, siete vintages y trazabilidad hasta el Country Report 26/84")

    cards = [
        ("Cobertura histórica", "2014-2025"),
        ("Horizonte de proyección", "2026-2031"),
        ("Última actualización", "Abril de 2026"),
    ]
    for index, (label, value) in enumerate(cards):
        card_x = 48 + index * 230
        c.setFillColor(pdf_color("#123b5a"))
        c.roundRect(card_x, page_h - 284, 205, 70, 10, fill=1, stroke=0)
        c.setFillColor(pdf_color("#b9ccd8"))
        c.setFont("Helvetica", 8)
        c.drawString(card_x + 14, page_h - 238, label.upper())
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 17)
        c.drawString(card_x + 14, page_h - 267, value)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(48, page_h - 340, "Metodología")
    c.setFillColor(pdf_color("#d6e6ef"))
    c.setFont("Helvetica", 9.5)
    methodology = data["meta"]["actualMethodology"]
    draw_wrapped_text(c, methodology, 48, page_h - 360, 730, 13)
    c.setFillColor(pdf_color("#93aebb"))
    c.setFont("Helvetica", 8)
    c.drawString(48, 34, "Fuente canónica: forecasts.json | Validación: hashes SHA-256 y contraste directo de Table 1 del CR 26/84")
    c.showPage()

    for page_number, variable in enumerate(data["actual"], start=2):
        meta = variable_meta(data, variable)
        c.setFillColor(pdf_color(BG))
        c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
        c.setFillColor(pdf_color(NAVY))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(36, page_h - 38, meta["label"])
        c.setFillColor(pdf_color(SLATE))
        c.setFont("Helvetica", 9)
        c.drawRightString(page_w - 36, page_h - 36, f"Unidad: {meta['unit']} | {data['meta']['latestReport']}")
        draw_pdf_chart(c, data, variable, 36, 205, page_w - 72, 330)
        c.setFillColor(pdf_color(NAVY))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(36, 181, "Desempeño observado por vintage")
        c.setFillColor(pdf_color(SLATE))
        c.setFont("Helvetica", 7.5)
        c.drawString(230, 181, "Las métricas no son directamente comparables cuando N difiere.")
        draw_pdf_metrics(c, data, variable, 36, 39, page_w - 72)
        c.setFillColor(pdf_color(SLATE))
        c.setFont("Helvetica", 7)
        c.drawRightString(page_w - 36, 20, f"Página {page_number}")
        c.showPage()

    c.save()
    return output


def draw_wrapped_text(c: canvas.Canvas, text: str, x: float, y: float, width: float, leading: float) -> None:
    words = text.split()
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        if c.stringWidth(trial, "Helvetica", 9.5) <= width:
            line = trial
        else:
            c.drawString(x, y, line)
            y -= leading
            line = word
    if line:
        c.drawString(x, y, line)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default(size=size)


def dashed_line(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], fill: str, width: int, dash: int = 9) -> None:
    for start, end in zip(points, points[1:]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        distance = math.hypot(dx, dy)
        if distance == 0:
            continue
        steps = int(distance // dash) + 1
        for index in range(0, steps, 2):
            a = index / steps
            b = min((index + 1) / steps, 1)
            draw.line((start[0] + dx * a, start[1] + dy * a, start[0] + dx * b, start[1] + dy * b), fill=fill, width=width)


def draw_pillow_panel(draw: ImageDraw.ImageDraw, data: dict, variable: str, box: tuple[int, int, int, int]) -> None:
    left, top, right, bottom = box
    meta = variable_meta(data, variable)
    years, series = chart_series(data, variable)
    low, high = scale_bounds(series)
    plot = (left + 72, top + 66, right - 22, bottom - 58)
    px0, py0, px1, py1 = plot

    draw.rounded_rectangle(box, radius=16, fill="#ffffff", outline=GRID, width=2)
    draw.text((left + 20, top + 16), f"{meta['label']} ({meta['unit']})", font=font(24, True), fill=NAVY)
    for step in range(6):
        value = low + (high - low) * step / 5
        y = py1 - (py1 - py0) * step / 5
        draw.line((px0, y, px1, y), fill=GRID, width=1)
        label = format_number(value, 1)
        draw.text((px0 - 10, y), label, font=font(14), fill=SLATE, anchor="rm")
    for year in years:
        x = px0 + (year - years[0]) / max(1, years[-1] - years[0]) * (px1 - px0)
        if year == years[0] or year == years[-1] or year % 2 == 0:
            draw.text((x, py1 + 13), str(year), font=font(13), fill=SLATE, anchor="ma")

    actual_through = int(data["meta"]["actualThrough"])
    if actual_through < years[-1]:
        zone_x = px0 + (actual_through - years[0]) / (years[-1] - years[0]) * (px1 - px0)
        draw.rectangle((zone_x, py0, px1, py1), fill="#f0f6fa")
        dashed_line(draw, [(zone_x, py0), (zone_x, py1)], "#758899", 2, 8)

    for item in series:
        segments: list[list[tuple[float, float]]] = [[]]
        for year in years:
            if year in item["values"]:
                x = px0 + (year - years[0]) / max(1, years[-1] - years[0]) * (px1 - px0)
                y = py1 - (item["values"][year] - low) / max(1e-9, high - low) * (py1 - py0)
                segments[-1].append((x, y))
            elif segments[-1]:
                segments.append([])
        for points in [segment for segment in segments if len(segment) > 1]:
            if item["actual"]:
                draw.line(points, fill=item["color"], width=5, joint="curve")
            else:
                dashed_line(draw, points, item["color"], 3)
            radius = 4 if item["actual"] else 3
            for point in points:
                draw.ellipse((point[0] - radius, point[1] - radius, point[0] + radius, point[1] + radius), fill=item["color"])


def build_overview_png(root: Path, data: dict) -> Path:
    output = root / "charts" / "IMF_Ecuador_Real_vs_Pronosticos.png"
    image = Image.new("RGB", (2400, 3000), BG)
    draw = ImageDraw.Draw(image)
    draw.text((1200, 70), "Ecuador: historia revisada y pronósticos del FMI", font=font(48, True), fill=NAVY, anchor="ma")
    draw.text((1200, 130), "Ocho variables | siete vintages | actualizado con CR 26/84", font=font(24), fill=SLATE, anchor="ma")

    legend_y = 185
    legend_items = [("Histórico / estimado", ACTUAL)] + [(name, item["color"]) for name, item in data["vintages"].items()]
    total_width = sum(170 if index else 245 for index in range(len(legend_items)))
    cursor = (2400 - total_width) / 2
    for index, (name, color) in enumerate(legend_items):
        draw.line((cursor, legend_y, cursor + 35, legend_y), fill=color, width=5 if index == 0 else 3)
        draw.text((cursor + 44, legend_y), name, font=font(16), fill=SLATE, anchor="lm")
        cursor += 245 if index == 0 else 170

    variables = list(data["actual"])
    margin_x, gap_x, gap_y = 70, 34, 34
    panel_w = (2400 - margin_x * 2 - gap_x) // 2
    top = 235
    panel_h = (3000 - top - 70 - gap_y * 3) // 4
    for index, variable in enumerate(variables):
        row, col = divmod(index, 2)
        left = margin_x + col * (panel_w + gap_x)
        panel_top = top + row * (panel_h + gap_y)
        draw_pillow_panel(draw, data, variable, (left, panel_top, left + panel_w, panel_top + panel_h))

    image.save(output, quality=95, optimize=True)
    return output


def build_error_png(root: Path, data: dict) -> Path:
    output = root / "charts" / "IMF_Ecuador_Error_Pronostico.png"
    variables = ["Real GDP (%)", "Balance Fiscal NFPS (% PIB)", "Deuda Pública (% PIB)", "Cuenta Corriente (% PIB)"]
    image = Image.new("RGB", (2200, 1800), BG)
    draw = ImageDraw.Draw(image)
    draw.text((1100, 62), "Error histórico por vintage", font=font(46, True), fill=NAVY, anchor="ma")
    draw.text((1100, 118), "MAE: promedio del error absoluto | menor es mejor | N varía entre vintages", font=font(22), fill=SLATE, anchor="ma")

    margin_x, top, gap = 70, 170, 34
    panel_w = (2200 - margin_x * 2 - gap) // 2
    panel_h = (1800 - top - 60 - gap) // 2
    for index, variable in enumerate(variables):
        row, col = divmod(index, 2)
        left = margin_x + col * (panel_w + gap)
        panel_top = top + row * (panel_h + gap)
        box = (left, panel_top, left + panel_w, panel_top + panel_h)
        draw.rounded_rectangle(box, radius=16, fill="#ffffff", outline=GRID, width=2)
        meta = variable_meta(data, variable)
        draw.text((left + 22, panel_top + 18), f"{meta['label']} ({meta['unit']})", font=font(24, True), fill=NAVY)
        metrics = calculate_metrics(data, variable)
        observed = [metric for metric in metrics if metric["mae"] is not None]
        max_mae = max(metric["mae"] for metric in observed)
        bar_left, bar_right = left + 185, left + panel_w - 70
        start_y = panel_top + 90
        row_h = 82
        for metric_index, metric in enumerate(metrics):
            y = start_y + metric_index * row_h
            draw.text((left + 22, y + 15), metric["name"], font=font(18, True), fill=metric["color"])
            if metric["mae"] is None:
                draw.text((bar_left, y + 15), "Sin años observados", font=font(16), fill=SLATE)
                continue
            width = (bar_right - bar_left) * metric["mae"] / max_mae
            draw.rounded_rectangle((bar_left, y, bar_left + width, y + 36), radius=7, fill=metric["color"])
            draw.text((bar_left + width + 10, y + 18), f"{format_number(metric['mae'], meta['decimals'])} · N={metric['n']}", font=font(16), fill=SLATE, anchor="lm")

    image.save(output, quality=95, optimize=True)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    root = args.root.resolve()

    errors = validate_repository(root, verify_pdf=True)
    if errors:
        print("No se generaron artefactos porque la validación falló:")
        for error in errors:
            print(f"- {error}")
        return 1

    data = load_json(root / "forecasts.json")
    manifest = load_json(root / "data" / "source_manifest.json")
    outputs = [build_pdf(root, data, manifest), build_overview_png(root, data), build_error_png(root, data)]
    for output in outputs:
        print(f"Generado: {output.relative_to(root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
