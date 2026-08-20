"""Render portable CSV and static HTML market-monitoring reports."""

from __future__ import annotations

import csv
import html
import json
import math
import os
import sqlite3
from datetime import date
from pathlib import Path

from .analysis import AnalysisConfig, analyze_database, config_as_dict

CSV_FIELDS = [
    "prefecture_code", "prefecture_name", "target_year", "target_month", "base_year", "release_type",
    "total_guests", "average_occupancy_rate", "average_facilities", "facilities",
    "foreign_share_pct",
    "demand_vs_base_pct", "occupancy_vs_base_pp", "foreign_vs_base_pct",
    "demand_ltm_yoy_pct", "foreign_ltm_yoy_pct", "japanese_ltm_yoy_pct",
    "occupancy_ltm_yoy_pp", "facility_ltm_yoy_pct", "facility_yoy_pct",
    "foreign_share_yoy_pp",
    "recent_demand_yoy_pct", "recent_occupancy_yoy_pp", "monthly_cv", "peak_month_share_pct",
    "seasonal_occupancy_cv", "occupancy_seasonal_range_pp",
    "top3_demand_share_pct",
]


def _source_published_on(database: Path, config: AnalysisConfig) -> str:
    connection = sqlite3.connect(database)
    try:
        value = connection.execute(
            "SELECT published_on FROM source_files WHERE year = ? AND release_type = ?",
            (config.target_year, config.release_type),
        ).fetchone()
    finally:
        connection.close()
    return value[0] if value else "unknown"


def _display_date(value: str) -> str:
    """Convert an ISO publication date to a concise display label."""
    if value == "unknown":
        return value
    try:
        published_on = date.fromisoformat(value)
    except ValueError:
        return value
    return published_on.strftime("%Y/%m/%d")


def _serializable(row: dict) -> dict:
    return {key: row.get(key) for key in CSV_FIELDS}


def _write_csv(path: Path, rows: list[dict]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(_serializable(row) for row in rows)
    os.replace(temporary, path)


def _fmt(value: object, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.1f}{suffix}"
    if isinstance(value, int):
        return f"{value:,}{suffix}"
    return html.escape(str(value))


def _document(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root{{--ink:#172033;--muted:#637083;--line:#dce2ea;--paper:#fff;--bg:#f3f6f9;--accent:#155e75}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55}}
main{{max-width:1180px;margin:auto;padding:32px 20px 64px}}h1{{font-size:2rem;margin:.2rem 0}}h2{{margin-top:2rem}}.sub{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:22px 0}}.card,.panel{{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:16px}}
.metric{{font-size:1.45rem;font-weight:700}}table{{width:100%;border-collapse:collapse;background:var(--paper);font-size:.9rem}}th,td{{padding:9px;border:1px solid var(--line);text-align:left}}th{{background:#eaf0f5}}
a{{color:#075985}}.scroll{{overflow-x:auto}}
.axis{{margin-top:24px}}.axis h2{{margin:0}}.question{{color:var(--muted);margin:.25rem 0 1rem}}
.grid-2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}.rank{{font-weight:700;color:var(--muted);width:2rem}}.chart{{width:100%;height:auto;display:block}}.chart-note{{font-size:.82rem;color:var(--muted)}}
.market-kpis{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:22px 0}}.metric-detail{{font-size:.82rem;color:var(--muted);margin-top:6px}}.card-note{{font-size:.72rem;color:var(--muted);margin-top:8px}}
.demand-charts{{display:grid;grid-template-columns:1fr;gap:24px}}.chart-box{{min-width:0}}.chart-box h3{{margin:.1rem 0 .75rem;font-size:1rem}}
.numeric{{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}.range-value{{font-weight:700;color:#9a3412}}.month-pair{{text-align:center;white-space:nowrap}}
.table-tools{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:0 0 12px;flex-wrap:wrap}}.table-actions{{display:flex;align-items:center;gap:12px;flex-wrap:wrap}}.table-search{{width:min(320px,100%);border:1px solid #aeb8c5;border-radius:7px;padding:9px 11px;font:inherit;background:#fff;color:var(--ink)}}.export-button{{border:1px solid #0e7490;border-radius:7px;padding:9px 12px;background:#fff;color:#0e5f76;font:inherit;font-weight:700;cursor:pointer}}.export-button:hover{{background:#ecfeff}}.sortable button{{width:100%;border:0;background:transparent;padding:0;color:inherit;font:inherit;font-weight:700;text-align:right;cursor:pointer}}.sortable button::after{{content:" ↕";color:#64748b}}.sortable button[data-direction="asc"]::after{{content:" ↑"}}.sortable button[data-direction="desc"]::after{{content:" ↓"}}.th-group{{text-align:center;font-size:.82rem;letter-spacing:.04em}}.th-supply-demand{{background:#e0f2fe;border-top:3px solid #0284c7}}.th-inbound{{background:#fff7ed;border-top:3px solid #f59e0b}}.th-seasonality{{background:#f0fdf4;border-top:3px solid #16a34a}}.th-diff,.td-diff{{background:#f8fafc;border-left:1px dashed #94a3b8}}.change-positive{{color:#047857;font-weight:700}}.change-negative{{color:#b45309;font-weight:700}}.change-flat{{color:#64748b;font-weight:700}}
.prefecture-scroll{{position:relative}}#prefecture-table thead{{position:sticky;top:0;z-index:4}}#prefecture-table th:first-child,#prefecture-table td:first-child{{position:sticky;left:0;min-width:7.5rem;box-shadow:2px 0 0 var(--line)}}#prefecture-table thead th:first-child{{z-index:6;background:#eaf0f5}}#prefecture-table tbody td:first-child{{z-index:2;background:var(--paper)}}
@media(min-width:768px){{.market-kpis{{grid-template-columns:repeat(4,minmax(0,1fr))}}.demand-charts{{grid-template-columns:repeat(2,minmax(0,1fr))}}.prefecture-scroll{{max-height:70vh;overflow:auto}}}}@media(max-width:760px){{.grid-2{{grid-template-columns:1fr}}.table-tools{{align-items:stretch}}.table-search{{width:100%}}}}
@media print{{body{{background:#fff}}main{{max-width:none}}.panel,.card{{break-inside:avoid}}}}
</style></head><body><main>{body}</main></body></html>"""


def _load_time_series(database: Path, config: AnalysisConfig) -> tuple[dict[int, list[float]], dict[int, dict[int, list[dict]]]]:
    years = sorted({config.base_year, config.target_year - 2, config.target_year - 1, config.target_year})
    placeholders = ",".join("?" for _ in years)
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        national_rows = connection.execute(
            f"SELECT year, month, occupancy_rate FROM national_occupancy WHERE year IN ({placeholders}) ORDER BY year, month",
            years,
        ).fetchall()
        market_rows = connection.execute(
            f"SELECT * FROM monthly_market WHERE year IN ({placeholders}) ORDER BY prefecture_code, year, month",
            years,
        ).fetchall()
    finally:
        connection.close()
    national: dict[int, list[float]] = {}
    for item in national_rows:
        national.setdefault(item["year"], []).append(float(item["occupancy_rate"]))
    if any(len(national.get(year, [])) != 12 for year in years):
        raise ValueError(f"national occupancy must contain 12 months for {years}")
    prefectures: dict[int, dict[int, list[dict]]] = {}
    for item in market_rows:
        prefectures.setdefault(item["prefecture_code"], {}).setdefault(item["year"], []).append(dict(item))
    return national, prefectures


def _line_chart(
    series: dict[int, list[float]],
    *,
    y_label: str,
    suffix: str = "",
    reference_year: int | None = None,
    y_domain: tuple[float, float] | None = None,
) -> str:
    width, height = 760, 360
    left, right, top, bottom = 64, 24, 34, 54
    values = [value for yearly in series.values() for value in yearly]
    if y_domain is None:
        low, high = min(values), max(values)
        padding = (high - low) * 0.12 or 1
        low, high = max(0, low - padding), high + padding
    else:
        low, high = y_domain
    colors = ["#64748b", "#3b82f6", "#8b5cf6", "#0f766e"]

    def x(month: int) -> float:
        return left + (month - 1) / 11 * (width - left - right)

    def y(value: float) -> float:
        return top + (high - value) / (high - low) * (height - top - bottom)

    parts = [f'<rect x="{left}" y="{top}" width="{width-left-right}" height="{height-top-bottom}" fill="#f8fafc" stroke="#dce2ea"/>']
    for step in range(5):
        value = low + (high - low) * step / 4
        py = y(value)
        parts.append(f'<line x1="{left}" y1="{py:.1f}" x2="{width-right}" y2="{py:.1f}" stroke="#e2e8f0"/>')
        parts.append(f'<text x="{left-8}" y="{py+4:.1f}" text-anchor="end" font-size="11" fill="#475569">{value:.1f}{suffix}</text>')
    for month in range(1, 13):
        parts.append(f'<text x="{x(month):.1f}" y="{height-22}" text-anchor="middle" font-size="11" fill="#475569">{month}月</text>')
    for index, (year, yearly) in enumerate(sorted(series.items())):
        points = " ".join(f"{x(month):.1f},{y(value):.1f}" for month, value in enumerate(yearly, 1))
        dash = ' stroke-dasharray="7 5"' if year == reference_year else ""
        color = colors[index % len(colors)]
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{3 if year == max(series) else 2}"{dash}/>')
        for month, value in enumerate(yearly, 1):
            parts.append(f'<circle cx="{x(month):.1f}" cy="{y(value):.1f}" r="2.5" fill="{color}"><title>{year}年{month}月 {value:,.1f}{suffix}</title></circle>')
        legend_x = left + index * 105
        parts.append(f'<line x1="{legend_x}" y1="16" x2="{legend_x+24}" y2="16" stroke="{color}" stroke-width="4"{dash}/><text x="{legend_x+30}" y="20" font-size="13" font-weight="600" fill="#334155">{year}</text>')
    return f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(y_label)}の月次推移">{"".join(parts)}</svg>'


def _guest_axis_label(value: float) -> str:
    return f"{value / 10_000:.1f}万" if value >= 10_000 else f"{value:,.0f}"


def _monthly_demand_chart(history: dict[int, list[dict]], recent_years: list[int]) -> str:
    width, height = 600, 390
    left, right, top, bottom = 72, 18, 48, 48
    plot_width, plot_height = width - left - right, height - top - bottom
    maximum = max(item["total_guests"] for year in recent_years for item in history[year]) * 1.08
    colors = {recent_years[0]: "#3b82f6", recent_years[1]: "#8b5cf6", recent_years[2]: "#0f766e"}

    def x(month: int) -> float:
        return left + (month - 1) / 11 * plot_width

    def y(value: float) -> float:
        return top + (1 - value / maximum) * plot_height

    parts = [f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#f8fafc" stroke="#dce2ea"/>']
    for step in range(5):
        value = maximum * step / 4
        py = y(value)
        parts.append(f'<line x1="{left}" y1="{py:.1f}" x2="{width-right}" y2="{py:.1f}" stroke="#e2e8f0"/>')
        parts.append(f'<text x="{left-8}" y="{py+4:.1f}" text-anchor="end" font-size="11" fill="#475569">{_guest_axis_label(value)}</text>')
    for index, year in enumerate(recent_years):
        color = colors[year]
        points = " ".join(f"{x(item['month']):.1f},{y(item['total_guests']):.1f}" for item in history[year])
        parts.append(f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="{3 if year == max(recent_years) else 2.5}"/>')
        for item in history[year]:
            parts.append(f'<circle cx="{x(item["month"]):.1f}" cy="{y(item["total_guests"]):.1f}" r="3" fill="{color}"><title>{year}年{item["month"]}月 {item["total_guests"]:,}人泊</title></circle>')
        legend_x = left + index * 130
        parts.append(f'<line x1="{legend_x}" y1="22" x2="{legend_x+30}" y2="22" stroke="{color}" stroke-width="4"/><text x="{legend_x+37}" y="27" font-size="14" font-weight="600" fill="#334155">{year}年</text>')
    for month in range(1, 13):
        parts.append(f'<text x="{x(month):.1f}" y="{height-18}" text-anchor="middle" font-size="11" fill="#475569">{month}月</text>')
    return f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="直近3年の総延べ宿泊者数・月次推移">{"".join(parts)}</svg>'


def _annual_demand_structure_chart(history: dict[int, list[dict]], recent_years: list[int]) -> str:
    width, height = 600, 390
    left, right, top, bottom = 72, 64, 48, 52
    plot_width, plot_height = width - left - right, height - top - bottom
    annual = []
    for year in recent_years:
        japanese = sum(item["japanese_guests"] or 0 for item in history[year])
        foreign = sum(item["foreign_guests"] or 0 for item in history[year])
        total = japanese + foreign
        annual.append((year, japanese, foreign, foreign / total * 100 if total else 0))
    maximum = max(japanese + foreign for _, japanese, foreign, _ in annual) * 1.10
    share_max = min(100.0, max(10.0, math.ceil(max(share for *_, share in annual) / 10) * 10))

    def x(index: int) -> float:
        return left + (index + 0.5) / 3 * plot_width

    def guest_y(value: float) -> float:
        return top + (1 - value / maximum) * plot_height

    def share_y(value: float) -> float:
        return top + (1 - value / share_max) * plot_height

    parts = [f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" fill="#f8fafc" stroke="#dce2ea"/>']
    for step in range(5):
        value = maximum * step / 4
        py = guest_y(value)
        parts.append(f'<line x1="{left}" y1="{py:.1f}" x2="{width-right}" y2="{py:.1f}" stroke="#e2e8f0"/>')
        parts.append(f'<text x="{left-8}" y="{py+4:.1f}" text-anchor="end" font-size="11" fill="#475569">{_guest_axis_label(value)}</text>')
    bar_width = 78
    share_points = []
    for index, (year, japanese, foreign, share) in enumerate(annual):
        px = x(index)
        domestic_top = guest_y(japanese)
        total_top = guest_y(japanese + foreign)
        base = top + plot_height
        parts.append(f'<rect x="{px-bar_width/2:.1f}" y="{domestic_top:.1f}" width="{bar_width}" height="{base-domestic_top:.1f}" fill="#334155"><title>{year}年 日本人 {japanese:,}人泊</title></rect>')
        parts.append(f'<rect x="{px-bar_width/2:.1f}" y="{total_top:.1f}" width="{bar_width}" height="{domestic_top-total_top:.1f}" fill="#f59e0b"><title>{year}年 外国人 {foreign:,}人泊</title></rect>')
        share_points.append(f"{px:.1f},{share_y(share):.1f}")
        parts.append(f'<text x="{px:.1f}" y="{height-19}" text-anchor="middle" font-size="13" font-weight="600" fill="#334155">{year}年</text>')
    parts.append(f'<polyline points="{" ".join(share_points)}" fill="none" stroke="#0ea5e9" stroke-width="3.5"/>')
    for index, (*_, share) in enumerate(annual):
        parts.append(f'<circle cx="{x(index):.1f}" cy="{share_y(share):.1f}" r="4" fill="#0ea5e9"><title>外国人比率 {share:.1f}%</title></circle>')
    parts.append(f'<text x="{left}" y="25" font-size="13" font-weight="600" fill="#334155">■ 日本人</text><text x="{left+94}" y="25" font-size="13" font-weight="600" fill="#d97706">■ 外国人</text><text x="{left+188}" y="25" font-size="13" font-weight="600" fill="#0284c7">━ 外国人比率（右軸）</text>')
    for step in range(3):
        value = share_max * step / 2
        parts.append(f'<text x="{width-right+8}" y="{share_y(value)+4:.1f}" font-size="11" fill="#0369a1">{value:.0f}%</text>')
    return f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="年次需要構造と外国人比率">{"".join(parts)}</svg>'


def _annual_facilities_chart(history: dict[int, list[dict]], years: list[int]) -> str:
    """Render December surveyed-facility counts for the requested years."""
    annual = []
    for year in years:
        december = next((item for item in history[year] if item["month"] == 12), None)
        if december is None:
            raise ValueError(f"facility chart requires December data for {year}")
        annual.append((year, int(december["facilities"])))

    width, height = 760, 360
    left, right, top, bottom = 72, 24, 48, 58
    plot_width, plot_height = width - left - right, height - top - bottom
    maximum = max(value for _, value in annual) * 1.18 or 1

    def x(index: int) -> float:
        return left + (index + 0.5) / len(annual) * plot_width

    def y(value: float) -> float:
        return top + (1 - value / maximum) * plot_height

    parts = [
        (
            f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" '
            'fill="#f8fafc" stroke="#dce2ea"/>'
        )
    ]
    for step in range(5):
        value = maximum * step / 4
        py = y(value)
        parts.append(
            f'<line x1="{left}" y1="{py:.1f}" x2="{width-right}" y2="{py:.1f}" '
            'stroke="#e2e8f0"/>'
        )
        parts.append(
            f'<text x="{left-8}" y="{py+4:.1f}" text-anchor="end" font-size="11" '
            f'fill="#475569">{value:,.0f}</text>'
        )
    bar_width = min(92, plot_width / len(annual) * 0.5)
    for index, (year, value) in enumerate(annual):
        px, py = x(index), y(value)
        base = top + plot_height
        parts.append(
            f'<rect x="{px-bar_width/2:.1f}" y="{py:.1f}" width="{bar_width:.1f}" '
            f'height="{base-py:.1f}" fill="#0f766e"><title>{year}年12月 {value:,}施設</title></rect>'
        )
        parts.append(
            f'<text x="{px:.1f}" y="{py-9:.1f}" text-anchor="middle" font-size="12" '
            f'font-weight="700" fill="#172033">{value:,}施設</text>'
        )
        parts.append(
            f'<text x="{px:.1f}" y="{height-22}" text-anchor="middle" font-size="12" '
            f'fill="#475569">{year}年</text>'
        )
    return (
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="調査対象施設数の年次推移">{"".join(parts)}</svg>'
    )


def _market_sheet(row: dict, published_on: str, history: dict[int, list[dict]], config: AnalysisConfig) -> str:
    recent_years = [config.target_year - 2, config.target_year - 1, config.target_year]
    comparison_years = [config.base_year, *recent_years]
    occupancy = {year: [item["occupancy_rate"] for item in history[year]] for year in [config.base_year, *recent_years]}
    current_facilities = int(history[config.target_year][config.target_month - 1]["facilities"])
    previous_facilities = int(history[config.target_year - 1][config.target_month - 1]["facilities"])
    base_facilities = int(history[config.base_year][config.target_month - 1]["facilities"])
    card_html = "".join(
        [
            f'<div class="card"><div class="sub">LTM平均客室稼働率</div><div class="metric">{_fmt(row["average_occupancy_rate"], "%")}</div><div class="metric-detail">前年差: {row["occupancy_ltm_yoy_pp"]:+.1f}pt ／ {config.base_year}年差: {row["occupancy_vs_base_pp"]:+.1f}pt</div></div>',
            f'<div class="card"><div class="sub">LTM外国人延べ宿泊者比率</div><div class="metric">{_fmt(row["foreign_share_pct"], "%")}</div><div class="metric-detail">前年差: {row["foreign_share_yoy_pp"]:+.1f}pt</div></div>',
            f'<div class="card"><div class="sub">LTM総延べ宿泊者数</div><div class="metric">{int(row["total_guests"]):,}人泊</div><div class="metric-detail">前年比: {row["demand_ltm_yoy_pct"]:+.1f}%</div></div>',
            f'<div class="card"><div class="sub">宿泊施設数（{config.target_year}年{config.target_month}月）</div><div class="metric">{current_facilities:,}施設</div><div class="metric-detail">前年差: {current_facilities-previous_facilities:+,}施設 ／ {config.base_year}年差: {current_facilities-base_facilities:+,}施設</div><div class="card-note">客室数ではなく、調査対象の施設数です。</div></div>',
        ]
    )
    body = f"""<a href="../index.html">← 全国ダッシュボード</a><h1>{html.escape(row['prefecture_name'])} Market Sheet</h1>
<p class="sub">対象年：{config.target_year}年確定値／データ公表日 {html.escape(_display_date(published_on))}</p>
<div class="market-kpis">{card_html}</div>
<section class="panel axis"><h2>1. 客室稼働率</h2><p class="question">直近3年の月次推移を、コロナ禍前の{config.base_year}年と比較します。</p>{_line_chart(occupancy, y_label="客室稼働率", suffix="%", reference_year=config.base_year, y_domain=(0, 100))}</section>
<section class="panel axis"><h2>2. 延べ宿泊者数（需要）</h2><p class="question">直近3年の月次総需要トレンドと、年次での需要構造（日本人・外国人比率）の変化を確認します。</p>
<div class="demand-charts">
<div class="chart-box"><h3>総延べ宿泊者数・月次推移（直近3年）</h3>{_monthly_demand_chart(history, recent_years)}</div>
<div class="chart-box"><h3>年次需要構造と外国人比率（直近3年）</h3>{_annual_demand_structure_chart(history, recent_years)}</div>
</div></section>
<section class="panel axis"><h2>3. 宿泊施設数（供給）</h2><p class="question">調査対象施設数の年次推移（{config.base_year}年・直近3年）を確認し、供給環境の変化を把握します。</p>{_annual_facilities_chart(history, comparison_years)}<p class="chart-note">各年12月時点。客室数ではなく、調査対象の施設数です。</p></section>"""
    return _document(f"{row['prefecture_name']} Market Sheet", body)


def _prefecture_cell(row: dict) -> str:
    return f'<a href="market-sheets/{row["prefecture_code"]:02}.html">{html.escape(row["prefecture_name"])}</a>'


def _prefecture_table(rows: list[dict]) -> str:
    def change_class(value: float) -> str:
        displayed_value = round(value, 1)
        if displayed_value > 0:
            return "change-positive"
        if displayed_value < 0:
            return "change-negative"
        return "change-flat"

    body = []
    for row in rows:
        occupancy = row["monthly_occupancy_rate"]
        labels = row["monthly_labels"]
        peak_month = int(labels[occupancy.index(max(occupancy))].split("-")[1])
        bottom_month = int(labels[occupancy.index(min(occupancy))].split("-")[1])
        cells = [
            (_prefecture_cell(row), row["prefecture_name"], ""),
            (f'{row["average_occupancy_rate"]:.1f}%', row["average_occupancy_rate"], "numeric"),
            (f'{row["occupancy_ltm_yoy_pp"]:+.1f}pt', row["occupancy_ltm_yoy_pp"], f'numeric td-diff {change_class(row["occupancy_ltm_yoy_pp"])}'),
            (f'{row["total_guests"]:,.0f}人泊', row["total_guests"], "numeric"),
            (f'{row["demand_ltm_yoy_pct"]:+.1f}%', row["demand_ltm_yoy_pct"], f'numeric td-diff {change_class(row["demand_ltm_yoy_pct"])}'),
            (f'{row["facilities"]:,.0f}施設', row["facilities"], "numeric"),
            (f'{row["facility_yoy_pct"]:+.1f}%', row["facility_yoy_pct"], f'numeric td-diff {change_class(row["facility_yoy_pct"])}'),
            (f'{row["foreign_share_pct"]:.1f}%', row["foreign_share_pct"], "numeric"),
            (f'{row["foreign_ltm_yoy_pct"]:+.1f}%', row["foreign_ltm_yoy_pct"], f'numeric td-diff {change_class(row["foreign_ltm_yoy_pct"])}'),
            (f'{row["seasonal_occupancy_cv"]:.3f}', row["seasonal_occupancy_cv"], "numeric"),
            (f'<span class="range-value">{row["occupancy_seasonal_range_pp"]:.1f}pt</span>', row["occupancy_seasonal_range_pp"], "numeric"),
            (f"{peak_month}月 / {bottom_month}月", f"{peak_month:02d}-{bottom_month:02d}", "month-pair"),
        ]
        body.append(
            "<tr>"
            + "".join(
                f'<td class="{css_class}" data-sort="{sort_value}">{display}</td>'
                for display, sort_value, css_class in cells
            )
            + "</tr>"
        )
    second_row = [
        (1, "LTM平均稼働率", ""),
        (2, "稼働率 前年差", "th-diff"),
        (3, "延べ宿泊者数", ""),
        (4, "宿泊者数 前年比", "th-diff"),
        (5, "宿泊施設数", ""),
        (6, "施設数 前年比", "th-diff"),
        (7, "外国人比率", ""),
        (8, "外国人客数 前年比", "th-diff"),
        (9, "Seasonal CV", ""),
        (10, "繁閑レンジ", ""),
        (11, "ピーク月 / ボトム月", ""),
    ]
    detail_headers = "".join(
        f'<th class="sortable numeric {css_class}"><button type="button" data-column="{index}" aria-label="{html.escape(label)}で並べ替え">{html.escape(label)}</button></th>'
        for index, label, css_class in second_row
    )
    group_headers = '''<tr><th rowspan="2">都道府県</th><th colspan="6" class="th-group th-supply-demand">需給</th><th colspan="2" class="th-group th-inbound">インバウンド</th><th colspan="3" class="th-group th-seasonality">季節変動</th></tr>'''
    return f'''<div class="table-tools"><input id="prefecture-search" class="table-search" type="search" placeholder="都道府県名で検索" aria-label="都道府県名で検索"><div class="table-actions"><span id="prefecture-count" class="sub">{len(rows)}県</span><button id="prefecture-export" class="export-button" type="button">表示中データをCSVダウンロード</button></div></div>
<div class="scroll prefecture-scroll" tabindex="0" aria-label="都道府県別指標テーブル"><table id="prefecture-table"><thead>{group_headers}<tr>{detail_headers}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'''


def _index_html(
    rows: list[dict], config: AnalysisConfig, published_on: str, national: dict[int, list[float]]
) -> str:
    # Each monthly rate is the official nationwide ratio of occupied room-nights
    # to total room-nights. These KPIs are arithmetic means of the 12 published
    # monthly rates, not the Tourism Agency's room-night-weighted annual rate.
    target_average = sum(national[config.target_year]) / 12
    previous_average = sum(national[config.target_year - 1]) / 12
    base_average = sum(national[config.base_year]) / 12
    national_series = {
        year: national[year]
        for year in [config.base_year, config.target_year - 2, config.target_year - 1, config.target_year]
    }
    prefecture_table = _prefecture_table(rows)
    body = f"""<h1>都道府県別ホテルマーケットレポート</h1><p class="sub">対象年：{config.target_year}年確定値／データ公表日 {html.escape(_display_date(published_on))}</p><p><a href="municipalities/index.html">市区町村別ホテルマーケットレポート →</a></p>
<section class="panel axis"><h2>1. 全国のホテル市況</h2><p class="question">月次の全国客室稼働率は、全国の利用客室数 ÷ 全国の総客室数で算出された観光庁公表値です。都道府県別稼働率の単純平均ではありません。KPIは月次公表値12か月の単純平均です。</p>{_line_chart(national_series, y_label="全国客室稼働率", suffix="%", reference_year=config.base_year, y_domain=(0, 100))}<div class="cards"><div class="card"><div class="sub">{config.target_year}年 月次全国値の平均</div><div class="metric">{target_average:.1f}%</div></div><div class="card"><div class="sub">前年平均との差</div><div class="metric">{target_average-previous_average:+.1f}pt</div></div><div class="card"><div class="sub">{config.base_year}年平均との差</div><div class="metric">{target_average-base_average:+.1f}pt</div></div></div></section>
<section class="panel axis"><h2>2. 都道府県一覧</h2><p class="question">県名をクリックすると時系列Market Sheetを表示します。列見出しで並べ替え、検索欄で絞り込めます。</p><p class="chart-note">※ Seasonal CV（変動係数）＝ 各都道府県の月次客室稼働率（12か月）の標準偏差（σ） ÷ 年間平均客室稼働率（μ）<br>※ 繁閑レンジ ＝ 年間における月次客室稼働率の最高値（ピーク月）と最低値（ボトム月）のポイント差（pt）</p>{prefecture_table}</section>
<script>
(()=>{{
const table=document.querySelector('#prefecture-table');
if(!table)return;
const body=table.tBodies[0],search=document.querySelector('#prefecture-search'),count=document.querySelector('#prefecture-count'),exportButton=document.querySelector('#prefecture-export');
let direction=1,column=-1;
const visibleRows=()=>[...body.rows].filter(row=>!row.hidden);
const update=()=>{{const query=search.value.trim().toLocaleLowerCase('ja');[...body.rows].forEach(row=>{{row.hidden=!row.cells[0].textContent.toLocaleLowerCase('ja').includes(query)}});count.textContent=`${{visibleRows().length}}県`;}};
search.addEventListener('input',update);
table.querySelectorAll('button[data-column]').forEach(button=>button.addEventListener('click',()=>{{const next=Number(button.dataset.column);direction=column===next?-direction:1;column=next;table.querySelectorAll('button[data-column]').forEach(item=>item.removeAttribute('data-direction'));button.dataset.direction=direction===1?'asc':'desc';const rows=[...body.rows];rows.sort((a,b)=>{{const av=a.cells[column].dataset.sort,bv=b.cells[column].dataset.sort,an=Number(av),bn=Number(bv);const result=Number.isNaN(an)||Number.isNaN(bn)?av.localeCompare(bv,'ja'):an-bn;return result*direction;}});rows.forEach(row=>body.appendChild(row));}}));
exportButton.addEventListener('click',()=>{{
const headers=['都道府県',...[...table.querySelectorAll('thead tr:last-child button')].map(button=>button.textContent.trim())];
const data=visibleRows().map(row=>[...row.cells].map(cell=>cell.textContent.trim()));
const escapeCsv=value=>'"'+value.replaceAll('"','""')+'"';
const csv=[headers,...data].map(row=>row.map(escapeCsv).join(',')).join('\\r\\n');
const url=URL.createObjectURL(new Blob(['\\ufeff',csv],{{type:'text/csv;charset=utf-8'}}));
const link=document.createElement('a');link.href=url;link.download='prefecture-hotel-market-{config.target_year}.csv';link.click();URL.revokeObjectURL(url);
}});
}})();
</script>"""
    return _document("都道府県別ホテルマーケットレポート", body)


def generate_reports(database: Path, output_dir: Path, config: AnalysisConfig) -> dict:
    rows = analyze_database(database, config)
    national, histories = _load_time_series(database, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    sheets = output_dir / "market-sheets"
    sheets.mkdir(exist_ok=True)
    published_on = _source_published_on(database, config)
    _write_csv(output_dir / "prefecture-market.csv", rows)
    (output_dir / "index.html").write_text(
        _index_html(rows, config, published_on, national), encoding="utf-8"
    )
    for row in rows:
        (sheets / f"{row['prefecture_code']:02}.html").write_text(
            _market_sheet(row, published_on, histories[row["prefecture_code"]], config),
            encoding="utf-8",
        )
    metadata = {
        "published_on": published_on,
        "rows": len(rows),
        "config": config_as_dict(config),
    }
    (output_dir / "report-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"report": str(output_dir / "index.html"), "market_sheets": len(rows)}
