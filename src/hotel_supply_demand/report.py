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
    "total_guests", "average_occupancy_rate", "average_facilities", "foreign_share_pct",
    "demand_vs_base_pct", "occupancy_vs_base_pp", "foreign_vs_base_pct",
    "demand_ltm_yoy_pct", "foreign_ltm_yoy_pct", "japanese_ltm_yoy_pct",
    "occupancy_ltm_yoy_pp", "facility_ltm_yoy_pct", "foreign_share_yoy_pp",
    "recent_demand_yoy_pct", "recent_occupancy_yoy_pp", "monthly_cv", "peak_month_share_pct",
    "seasonal_occupancy_cv", "seasonal_occupancy_cv_percentile",
    "seasonal_occupancy_cv_relative", "occupancy_seasonal_range_pp",
    "top3_demand_share_pct",
    "top3_demand_share_pct_percentile", "top3_demand_share_pct_relative",
    "demand_ltm_yoy_pct_percentile", "demand_ltm_yoy_pct_relative",
    "foreign_share_pct_percentile", "foreign_share_pct_relative",
    "facility_ltm_yoy_pct_percentile", "facility_ltm_yoy_pct_relative",
    "recent_demand_yoy_pct_percentile", "recent_demand_yoy_pct_relative",
    "recovery_direction", "demand_mix_direction", "momentum_direction",
    "supply_demand_direction", "supply_demand_pattern", "market_state",
    "market_characteristics", "recovery_signals", "demand_mix_signals",
    "momentum_signals", "supply_demand_signals", "seasonality_signals",
    "is_watch", "signals", "watch_reasons",
    "observed_fact", "interpretation", "next_action", "data_quality_note",
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
    result = {key: row.get(key) for key in CSV_FIELDS}
    for field in (
        "market_characteristics",
        "recovery_signals",
        "demand_mix_signals",
        "momentum_signals",
        "supply_demand_signals",
        "seasonality_signals",
        "signals",
        "watch_reasons",
    ):
        result[field] = " / ".join(row[field])
    return result


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
:root{{--ink:#172033;--muted:#637083;--line:#dce2ea;--paper:#fff;--bg:#f3f6f9;--watch:#a73b27;--accent:#155e75}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55}}
main{{max-width:1180px;margin:auto;padding:32px 20px 64px}}h1{{font-size:2rem;margin:.2rem 0}}h2{{margin-top:2rem}}.sub{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px;margin:22px 0}}.card,.panel{{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:16px}}
.metric{{font-size:1.45rem;font-weight:700}}table{{width:100%;border-collapse:collapse;background:var(--paper);font-size:.9rem}}th,td{{padding:9px;border:1px solid var(--line);text-align:left}}th{{background:#eaf0f5}}tr.watch td:first-child{{border-left:4px solid var(--watch)}}
a{{color:#075985}}.scroll{{overflow-x:auto}}
.review{{border:1px solid #d97706;background:#fff7ed;color:#9a3412;border-radius:10px;padding:12px 16px;margin-bottom:20px;font-weight:600}}
.axis{{margin-top:24px}}.axis h2{{margin:0}}.question{{color:var(--muted);margin:.25rem 0 1rem}}
.grid-2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}}.rank{{font-weight:700;color:var(--muted);width:2rem}}.chart{{width:100%;height:auto;display:block}}.chart-note{{font-size:.82rem;color:var(--muted)}}
.market-kpis{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:22px 0}}.metric-detail{{font-size:.82rem;color:var(--muted);margin-top:6px}}.card-note{{font-size:.72rem;color:var(--muted);margin-top:8px}}
.demand-charts{{display:grid;grid-template-columns:1fr;gap:24px}}.chart-box{{min-width:0}}.chart-box h3{{margin:.1rem 0 .75rem;font-size:1rem}}
.breadth{{display:flex;flex-wrap:wrap;gap:8px;margin:14px 0}}.status{{background:#eef6f8;border:1px solid #bae6ed;border-radius:999px;padding:6px 11px;font-size:.84rem;color:#164e63}}
.numeric{{display:block;text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}}.range-value{{font-weight:700;color:#9a3412}}
.table-tools{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin:0 0 12px}}.table-search{{width:min(320px,100%);border:1px solid #aeb8c5;border-radius:7px;padding:9px 11px;font:inherit;background:#fff;color:var(--ink)}}.sortable button{{width:100%;border:0;background:transparent;padding:0;color:inherit;font:inherit;font-weight:700;text-align:left;cursor:pointer}}.sortable button::after{{content:" ↕";color:#64748b}}.sortable button[data-direction="asc"]::after{{content:" ↑"}}.sortable button[data-direction="desc"]::after{{content:" ↓"}}.trend{{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:700}}.trend.up{{background:#dff7ed;color:#166534}}.trend.down{{background:#fee2e2;color:#991b1b}}.trend.flat{{background:#eef2f7;color:#475569}}
@media(min-width:768px){{.market-kpis{{grid-template-columns:repeat(4,minmax(0,1fr))}}.demand-charts{{grid-template-columns:repeat(2,minmax(0,1fr))}}}}@media(max-width:760px){{.grid-2{{grid-template-columns:1fr}}}}
@media print{{body{{background:#fff}}main{{max-width:none}}.panel,.card{{break-inside:avoid}}}}
</style></head><body><main><div class="review">レビュー前・暫定版：LTM／直近3か月／全国相対評価の分析ロジックと生成結果は未レビューです。</div>{body}</main></body></html>"""


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


def _line_chart(series: dict[int, list[float]], *, y_label: str, suffix: str = "", reference_year: int | None = None) -> str:
    width, height = 760, 360
    left, right, top, bottom = 64, 24, 34, 54
    values = [value for yearly in series.values() for value in yearly]
    low, high = min(values), max(values)
    padding = (high - low) * 0.12 or 1
    low, high = max(0, low - padding), high + padding
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


def _market_sheet(row: dict, published_on: str, history: dict[int, list[dict]], config: AnalysisConfig) -> str:
    recent_years = [config.target_year - 2, config.target_year - 1, config.target_year]
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
<p class="sub">{config.target_year}年確定値／データ公表日 {html.escape(_display_date(published_on))}</p>
<div class="market-kpis">{card_html}</div>
<section class="panel axis"><h2>延べ宿泊者数</h2><p class="question">直近3年の月次総需要トレンドと、年次での需要構造（日本人・外国人比率）の変化を確認します。</p>
<div class="demand-charts">
<div class="chart-box"><h3>総延べ宿泊者数・月次推移（直近3年）</h3>{_monthly_demand_chart(history, recent_years)}</div>
<div class="chart-box"><h3>年次需要構造と外国人比率（{recent_years[0]}–{recent_years[-1]}年）</h3>{_annual_demand_structure_chart(history, recent_years)}</div>
</div></section>
<section class="panel axis"><h2>客室稼働率</h2><p class="question">直近3年の月次推移を、コロナ禍前の{config.base_year}年と比較します。</p>{_line_chart(occupancy, y_label="客室稼働率", suffix="%", reference_year=config.base_year)}</section>
<section class="panel axis"><h2>利用上の注意</h2><p>都道府県単位のマクロ統計であり、個別ホテルのADR、RevPAR、GOP、客室数、収益性や担保価値を直接示すものではありません。</p></section>"""
    return _document(f"{row['prefecture_name']} Market Sheet", body)


def _prefecture_cell(row: dict) -> str:
    return f'<a href="market-sheets/{row["prefecture_code"]:02}.html">{html.escape(row["prefecture_name"])}</a>'


def _table(headers: list[str], body_rows: list[list[str]]) -> str:
    header = "".join(f"<th>{html.escape(value)}</th>" for value in headers)
    body = "".join("<tr>" + "".join(f"<td>{value}</td>" for value in row) + "</tr>" for row in body_rows)
    return f'<div class="scroll"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>'


def _ranking_table(headers: list[str], rows: list[list[str]]) -> str:
    if not rows:
        return '<p class="sub">該当市場なし</p>'
    ranked = [[f'<span class="rank">{index}</span>', *row] for index, row in enumerate(rows, 1)]
    return _table(["順位", *headers], ranked)


def _occupancy_badge(value: float) -> str:
    css_class = "up" if value > 1 else "down" if value < -1 else "flat"
    return f'<span class="trend {css_class}">{value:+.1f}pt</span>'


def _prefecture_table(rows: list[dict]) -> str:
    headers = ["都道府県", "LTM平均客室稼働率", "客室稼働率前年差", "外国人延べ宿泊者比率", "宿泊施設数（前年比）"]
    body = []
    for row in rows:
        cells = [
            (_prefecture_cell(row), row["prefecture_name"]),
            (_fmt(row["average_occupancy_rate"], "%"), row["average_occupancy_rate"]),
            (_occupancy_badge(row["occupancy_ltm_yoy_pp"]), row["occupancy_ltm_yoy_pp"]),
            (_fmt(row["foreign_share_pct"], "%"), row["foreign_share_pct"]),
            (f'{row["facilities"]:,.0f}施設 ({row["facility_yoy_pct"]:+.1f}%)', row["facilities"]),
        ]
        body.append("<tr>" + "".join(f'<td data-sort="{sort_value}">{display}</td>' for display, sort_value in cells) + "</tr>")
    header = "".join(
        f'<th class="sortable"><button type="button" data-column="{index}" aria-label="{html.escape(label)}で並べ替え">{html.escape(label)}</button></th>'
        for index, label in enumerate(headers)
    )
    return f'''<div class="table-tools"><input id="prefecture-search" class="table-search" type="search" placeholder="都道府県名で検索" aria-label="都道府県名で検索"><span id="prefecture-count" class="sub">{len(rows)}県</span></div>
<div class="scroll"><table id="prefecture-table"><thead><tr>{header}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'''


def _breadth(values: list[float], threshold: float = 1.0) -> tuple[int, int, int]:
    return (
        sum(value > threshold for value in values),
        sum(-threshold <= value <= threshold for value in values),
        sum(value < -threshold for value in values),
    )


def _index_html(
    rows: list[dict], config: AnalysisConfig, published_on: str, national: dict[int, list[float]]
) -> str:
    foreign_share_top = sorted(rows, key=lambda row: row["foreign_share_pct"], reverse=True)[:10]
    foreign_growth_top = sorted(rows, key=lambda row: row["foreign_ltm_yoy_pct"], reverse=True)[:10]
    seasonality_top = sorted(rows, key=lambda row: row["seasonal_occupancy_cv"], reverse=True)[:10]
    yoy_breadth = _breadth([row["occupancy_ltm_yoy_pp"] for row in rows])
    base_breadth = _breadth([row["occupancy_vs_base_pp"] for row in rows])
    target_average = sum(national[config.target_year]) / 12
    previous_average = sum(national[config.target_year - 1]) / 12
    base_average = sum(national[config.base_year]) / 12
    national_series = {
        year: national[year]
        for year in [config.base_year, config.target_year - 2, config.target_year - 1, config.target_year]
    }
    prefecture_table = _prefecture_table(rows)
    inbound_share_table = _ranking_table(
        ["都道府県", "外国人比率"],
        [[_prefecture_cell(row), f'<span class="numeric">{row["foreign_share_pct"]:.1f}%</span>'] for row in foreign_share_top],
    )
    inbound_growth_table = _ranking_table(
        ["都道府県", "外国人LTM YoY", "外国人比率"],
        [
            [
                _prefecture_cell(row),
                f'<span class="numeric">{row["foreign_ltm_yoy_pct"]:+.1f}%</span>',
                f'<span class="numeric">{row["foreign_share_pct"]:.1f}%</span>',
            ]
            for row in foreign_growth_top
        ],
    )
    seasonality_rows = []
    for row in seasonality_top:
        occupancy = row["monthly_occupancy_rate"]
        labels = row["monthly_labels"]
        peak_index = occupancy.index(max(occupancy))
        bottom_index = occupancy.index(min(occupancy))
        peak_month = int(labels[peak_index].split("-")[1])
        bottom_month = int(labels[bottom_index].split("-")[1])
        seasonality_rows.append(
            [
                _prefecture_cell(row),
                f'{row["seasonal_occupancy_cv"]:.3f}',
                f'<span class="range-value">{row["occupancy_seasonal_range_pp"]:.1f}pt</span>',
                f"{peak_month}月 / {bottom_month}月",
            ]
        )
    breadth_badges = f'''<div class="breadth" aria-label="市場回復の広がり">
<span class="status">稼働率前年比：上昇 {yoy_breadth[0]}県 / 横ばい {yoy_breadth[1]}県 / 低下 {yoy_breadth[2]}県</span>
<span class="status">{config.base_year}年比：上昇 {base_breadth[0]}県 / 横ばい {base_breadth[1]}県 / 低下 {base_breadth[2]}県</span>
</div>'''
    body = f"""<h1>全国 Hotel Market Monitor</h1><p class="sub">{config.target_year}年確定値／データ公表日 {html.escape(_display_date(published_on))}</p><p><a href="municipalities/index.html">市区町村 Hotel Market Monitor →</a></p>
<section class="panel axis"><h2>1. 全国のホテル市況</h2><p class="question">観光庁が公表する全国客室稼働率です。47都道府県の単純平均ではありません。</p>{_line_chart(national_series, y_label="全国客室稼働率", suffix="%", reference_year=config.base_year)}<div class="cards"><div class="card"><div class="sub">{config.target_year}年 全国平均稼働率</div><div class="metric">{target_average:.1f}%</div></div><div class="card"><div class="sub">前年平均との差</div><div class="metric">{target_average-previous_average:+.1f}pt</div></div><div class="card"><div class="sub">{config.base_year}年平均との差</div><div class="metric">{target_average-base_average:+.1f}pt</div></div></div>{breadth_badges}<p class="chart-note">平均値は観光庁の各月全国客室稼働率12値の単純平均です。広がりは都道府県別LTM平均差が+1.0pt超を上昇、±1.0pt以内を横ばい、-1.0pt未満を低下とします。</p></section>
<section class="axis"><h2>2. インバウンド</h2><div class="grid-2"><div class="panel"><h3>外国人宿泊者比率 TOP10</h3>{inbound_share_table}</div><div class="panel"><h3>外国人宿泊者数成長率 TOP10</h3>{inbound_growth_table}</div></div></section>
<section class="panel axis"><h2>3. 季節変動ランキング</h2><p class="question">季節性の良否判定ではなく、年間CFの繁閑差（ボトムリスク）を把握するための市場特性です。<br><small>※ Seasonal CV（変動係数）＝ 各都道府県の月次客室稼働率（12か月）の標準偏差（σ） ÷ 年間平均客室稼働率（μ）</small></p>{_ranking_table(["都道府県", "Seasonal CV（変動係数）", "稼働率の繁閑レンジ", "ピーク月 / ボトム月"], seasonality_rows)}</section>
<section class="panel axis"><h2>4. 都道府県一覧</h2><p class="question">県名をクリックすると時系列Market Sheetを表示します。列見出しで並べ替え、検索欄で絞り込めます。</p>{prefecture_table}</section>
<section class="panel axis"><h2>利用上の注意</h2><p>本レポートは担保物件所在地のマクロ市況を確認する一次資料です。個別ホテルのADR、RevPAR、GOP、収益性や担保価値を直接示すものではありません。</p></section>
<script>
(()=>{{const table=document.querySelector('#prefecture-table');if(!table)return;const body=table.tBodies[0],search=document.querySelector('#prefecture-search'),count=document.querySelector('#prefecture-count');let direction=1,column=-1;const visibleRows=()=>[...body.rows].filter(row=>!row.hidden);const update=()=>{{const query=search.value.trim().toLocaleLowerCase('ja');[...body.rows].forEach(row=>{{row.hidden=!row.cells[0].textContent.toLocaleLowerCase('ja').includes(query)}});count.textContent=`${{visibleRows().length}}県`;}};search.addEventListener('input',update);table.querySelectorAll('button[data-column]').forEach(button=>button.addEventListener('click',()=>{{const next=Number(button.dataset.column);direction=column===next?-direction:1;column=next;table.querySelectorAll('button[data-column]').forEach(item=>item.removeAttribute('data-direction'));button.dataset.direction=direction===1?'asc':'desc';const rows=[...body.rows];rows.sort((a,b)=>{{const av=a.cells[column].dataset.sort,bv=b.cells[column].dataset.sort,an=Number(av),bn=Number(bv);const result=Number.isNaN(an)||Number.isNaN(bn)?av.localeCompare(bv,'ja'):an-bn;return result*direction;}});rows.forEach(row=>body.appendChild(row));}}));}})();
</script>"""
    return _document("全国 Hotel Market Monitor", body)


def generate_reports(database: Path, output_dir: Path, config: AnalysisConfig) -> dict:
    rows = analyze_database(database, config)
    national, histories = _load_time_series(database, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    sheets = output_dir / "market-sheets"
    sheets.mkdir(exist_ok=True)
    published_on = _source_published_on(database, config)
    _write_csv(output_dir / "prefecture-market.csv", rows)
    (output_dir / "watchlist.csv").unlink(missing_ok=True)
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
