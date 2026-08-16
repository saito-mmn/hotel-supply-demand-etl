"""Generate static municipality market-monitoring reports from SQLite."""

from __future__ import annotations

import html
import json
import sqlite3
from datetime import date
from pathlib import Path


def _fmt(value: object, suffix: str = "") -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:,.1f}{suffix}"
    if isinstance(value, int):
        return f"{value:,}{suffix}"
    return html.escape(str(value))


def _document(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{--ink:#172033;--muted:#64748b;--line:#dce2ea;--paper:#fff;--bg:#f3f6f9;--accent:#155e75}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55}}
main{{max-width:1120px;margin:auto;padding:32px 20px 64px}}h1{{margin:.2rem 0}}h2{{margin:0 0 8px}}a{{color:#075985}}.sub,.note{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:22px 0}}.card,.panel{{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:16px}}.metric{{font-size:1.45rem;font-weight:700}}.metric-detail{{font-size:.8rem;color:var(--muted)}}
.panel{{margin-top:18px}}.grid-2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:#fff;font-size:.9rem}}th,td{{padding:9px;border:1px solid var(--line);text-align:left}}th{{background:#eaf0f5}}.numeric{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
.tools{{display:flex;gap:12px;align-items:center;margin:12px 0}}input,select{{border:1px solid #aeb8c5;border-radius:7px;padding:9px 11px;font:inherit;background:#fff}}input{{flex:1}}.chart{{width:100%;height:auto;display:block}}.period-badge{{display:inline-block;border-radius:999px;background:#e0f2fe;color:#075985;padding:2px 7px;margin-top:5px;font-size:.72rem;font-weight:700}}.warning-badge{{display:inline-block;border-radius:999px;background:#fff1f2;color:#be123c;border:1px solid #fecdd3;padding:1px 6px;margin-left:5px;font-size:.7rem;font-weight:700}}.center{{text-align:center;white-space:nowrap}}.sortable button{{width:100%;border:0;background:transparent;padding:0;color:inherit;font:inherit;font-weight:700;text-align:left;cursor:pointer;white-space:nowrap}}.sortable.numeric button{{text-align:right}}.sortable.center button{{text-align:center}}.sortable button::after{{content:" ↕";color:#64748b}}.sortable button[data-direction="asc"]::after{{content:" ↑"}}.sortable button[data-direction="desc"]::after{{content:" ↓"}}.th-group{{text-align:center;font-size:.82rem;letter-spacing:.04em}}.th-meta{{background:#f1f5f9;border-top:3px solid #64748b}}.th-supply-demand{{background:#e0f2fe;border-top:3px solid #0284c7}}.th-inbound{{background:#fff7ed;border-top:3px solid #f59e0b}}
@media(min-width:760px){{.cards{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}@media(max-width:760px){{.grid-2{{grid-template-columns:1fr}}}}
</style></head><body><main>{body}</main></body></html>"""


def _load(database: Path) -> tuple[list[dict], dict[int, list[dict]]]:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """SELECT m.id AS municipality_id,m.prefecture_code,m.prefecture_name,
                      m.municipality_name,f.year,f.month,f.total_guests,
                      f.japanese_guests,f.foreign_guests,f.occupied_rooms,
                      f.occupancy_rate,f.population_facilities,
                      f.responding_facilities,s.published_on,s.stat_inf_id
               FROM monthly_municipality_market AS f
               JOIN municipalities AS m ON m.id=f.municipality_id
               JOIN municipality_source_files AS s ON s.id=f.source_file_id
               WHERE f.room_size_class='total'
               ORDER BY m.prefecture_code,m.municipality_name,f.year,f.month"""
        ).fetchall()
    finally:
        connection.close()
    histories: dict[int, list[dict]] = {}
    for row in rows:
        histories.setdefault(row["municipality_id"], []).append(dict(row))
    latest = []
    for history in histories.values():
        row = history[-1]
        row["coverage_months"] = len(history)
        row["coverage_start"] = f'{history[0]["year"]}-{history[0]["month"]:02d}'
        row["coverage_end"] = f'{history[-1]["year"]}-{history[-1]["month"]:02d}'
        latest.append(row)
    return latest, histories


def _line_chart(history: list[dict], field: str, suffix: str, color: str) -> str:
    observed = {
        (row["year"], row["month"]): row[field]
        for row in history
        if row[field] is not None
    }
    if not observed:
        return '<p class="note">表章値がありません。</p>'
    first, last = min(observed), max(observed)
    periods: list[tuple[int, int]] = []
    year, month = first
    while (year, month) <= last:
        periods.append((year, month))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    width, height, left, right, top, bottom = 620, 285, 62, 18, 24, 66
    numeric = [float(value) for value in observed.values()]
    low, high = min(numeric), max(numeric)
    padding = (high - low) * .15 or max(high * .08, 1)
    low, high = max(0, low - padding), high + padding
    x = lambda index: left + (index / max(len(periods) - 1, 1)) * (width - left - right)
    y = lambda value: top + (high - value) / (high - low) * (height - top - bottom)
    parts = [f'<rect x="{left}" y="{top}" width="{width-left-right}" height="{height-top-bottom}" fill="#f8fafc" stroke="#dce2ea"/>']
    for step in range(4):
        value = low + (high - low) * step / 3
        py = y(value)
        label = f"{value:,.1f}" if suffix == "%" else f"{value:,.0f}"
        parts += [f'<line x1="{left}" y1="{py:.1f}" x2="{width-right}" y2="{py:.1f}" stroke="#e2e8f0"/>', f'<text x="{left-7}" y="{py+4:.1f}" text-anchor="end" font-size="11" fill="#475569">{label}{suffix}</text>']
    segment: list[str] = []
    for index, period in enumerate(periods):
        value = observed.get(period)
        if value is None:
            if len(segment) > 1:
                parts.append(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" stroke-width="3"/>')
            segment = []
        else:
            segment.append(f"{x(index):.1f},{y(float(value)):.1f}")
    if len(segment) > 1:
        parts.append(f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" stroke-width="3"/>')
    for index, (label_year, label_month) in enumerate(periods):
        value = observed.get((label_year, label_month))
        label = f"{str(label_year)[2:]}/{label_month:02d}" if index == 0 or label_month == 1 else f"{label_month}月"
        if index == 0 or index == len(periods) - 1 or label_month == 1 or index % 3 == 0:
            parts.append(f'<text x="{x(index):.1f}" y="{height-28}" text-anchor="end" transform="rotate(-45 {x(index):.1f} {height-28})" font-size="10" fill="#475569">{label}</text>')
        if value is not None:
            parts.append(f'<circle cx="{x(index):.1f}" cy="{y(float(value)):.1f}" r="3" fill="{color}"><title>{label_year}/{label_month:02d} {value:,.1f}{suffix}</title></circle>')
    return f'<svg viewBox="0 0 {width} {height}" class="chart" role="img">{"".join(parts)}</svg>'


def _seasonality_chart(
    history: list[dict], field: str, suffix: str, years: list[int]
) -> str:
    """Overlay monthly observations by calendar month for multi-year comparison."""
    series = {
        year: {
            row["month"]: row[field]
            for row in history
            if row["year"] == year and row[field] is not None
        }
        for year in years
    }
    numeric = [float(value) for monthly in series.values() for value in monthly.values()]
    if not numeric:
        return '<p class="note">比較対象期間に表章値がありません。</p>'

    width, height = 760, 360
    left, right, top, bottom = 64, 24, 52, 52
    plot_width, plot_height = width - left - right, height - top - bottom
    low, high = min(numeric), max(numeric)
    padding = (high - low) * 0.15 or max(high * 0.08, 1)
    low, high = max(0, low - padding), high + padding
    comparison_colors = ["#38bdf8", "#8b5cf6", "#0f766e"]
    comparison_years = [year for year in years if year != 2019]

    def x(month: int) -> float:
        return left + (month - 1) / 11 * plot_width

    def y(value: float) -> float:
        return top + (high - value) / (high - low) * plot_height

    parts = [
        (
            f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" '
            'fill="#f8fafc" stroke="#dce2ea"/>'
        )
    ]
    for step in range(5):
        value = low + (high - low) * step / 4
        py = y(value)
        label = f"{value:,.1f}" if suffix == "%" else f"{value:,.0f}"
        parts.append(
            f'<line x1="{left}" y1="{py:.1f}" x2="{width-right}" y2="{py:.1f}" '
            'stroke="#e2e8f0"/>'
        )
        parts.append(
            f'<text x="{left-8}" y="{py+4:.1f}" text-anchor="end" font-size="11" '
            f'fill="#475569">{label}{suffix}</text>'
        )
    for month in range(1, 13):
        parts.append(
            f'<text x="{x(month):.1f}" y="{height-20}" text-anchor="middle" '
            f'font-size="11" fill="#475569">{month}月</text>'
        )
    legend_x = left
    for index, year in enumerate(years):
        is_reference = year == 2019
        color = (
            "#64748b"
            if is_reference
            else comparison_colors[
                comparison_years.index(year) % len(comparison_colors)
            ]
        )
        dash = ' stroke-dasharray="7 5"' if is_reference else ""
        stroke_width = 2 if is_reference else 2.5
        monthly = series[year]
        segment: list[str] = []
        for month in range(1, 13):
            value = monthly.get(month)
            if value is None:
                if len(segment) > 1:
                    parts.append(
                        f'<polyline points="{" ".join(segment)}" fill="none" '
                        f'stroke="{color}" stroke-width="{stroke_width}"{dash}/>'
                    )
                segment = []
            else:
                segment.append(f"{x(month):.1f},{y(float(value)):.1f}")
        if len(segment) > 1:
            parts.append(
                f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" '
                f'stroke-width="{stroke_width}"{dash}/>'
            )
        for month, value in monthly.items():
            parts.append(
                f'<circle cx="{x(month):.1f}" cy="{y(float(value)):.1f}" r="3" '
                f'fill="{color}"><title>{year}年{month}月 {value:,.1f}{suffix}</title></circle>'
            )
        parts.append(
            f'<line x1="{legend_x}" y1="22" x2="{legend_x+24}" y2="22" '
            f'stroke="{color}" stroke-width="4"{dash}/>'
        )
        parts.append(
            f'<text x="{legend_x+30}" y="26" font-size="13" font-weight="600" '
            f'fill="#334155">{year}年</text>'
        )
        legend_x += 104
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        f'aria-label="{years[0]}年から{years[-1]}年の月次比較">{"".join(parts)}</svg>'
    )


def _annual_demand_chart(history: list[dict], years: list[int]) -> str:
    """Render annual demand only when all 12 monthly observations are comparable."""
    annual: list[tuple[int, int, int, float]] = []
    for year in years:
        rows = [row for row in history if row["year"] == year]
        months = {row["month"] for row in rows}
        complete = months == set(range(1, 13)) and all(
            row["total_guests"] is not None
            and row["japanese_guests"] is not None
            and row["foreign_guests"] is not None
            for row in rows
        )
        if not complete:
            return (
                '<p class="note">年間比較に必要な12か月分の掲載値が揃っていないため、'
                '年次需要構造は表示していません。</p>'
            )
        japanese = sum(int(row["japanese_guests"]) for row in rows)
        foreign = sum(int(row["foreign_guests"]) for row in rows)
        total = sum(int(row["total_guests"]) for row in rows)
        annual.append((year, japanese, foreign, foreign / total * 100 if total else 0.0))

    width, height = 620, 350
    left, right, top, bottom = 72, 62, 48, 52
    plot_width, plot_height = width - left - right, height - top - bottom
    maximum = max(japanese + foreign for _, japanese, foreign, _ in annual) * 1.15 or 1
    share_max = max(60.0, max(share for *_, share in annual) * 1.15)

    def x(index: int) -> float:
        return left + (index + 0.5) / len(annual) * plot_width

    def demand_y(value: float) -> float:
        return top + (1 - value / maximum) * plot_height

    def share_y(value: float) -> float:
        return top + (1 - value / share_max) * plot_height

    parts = [
        (
            f'<rect x="{left}" y="{top}" width="{plot_width}" height="{plot_height}" '
            'fill="#f8fafc" stroke="#dce2ea"/>'
        )
    ]
    for step in range(4):
        value = maximum * step / 3
        py = demand_y(value)
        parts.append(
            f'<line x1="{left}" y1="{py:.1f}" x2="{width-right}" y2="{py:.1f}" '
            'stroke="#e2e8f0"/>'
        )
        parts.append(
            f'<text x="{left-8}" y="{py+4:.1f}" text-anchor="end" font-size="11" '
            f'fill="#475569">{value/10000:,.1f}万</text>'
        )
    bar_width = min(76, plot_width / len(annual) * 0.48)
    share_points = []
    for index, (year, japanese, foreign, share) in enumerate(annual):
        px = x(index)
        japanese_top = demand_y(japanese)
        total_top = demand_y(japanese + foreign)
        base = top + plot_height
        parts.append(
            f'<rect x="{px-bar_width/2:.1f}" y="{japanese_top:.1f}" width="{bar_width:.1f}" '
            f'height="{base-japanese_top:.1f}" fill="#334155"><title>{year}年 日本人 '
            f'{japanese:,}人泊</title></rect>'
        )
        parts.append(
            f'<rect x="{px-bar_width/2:.1f}" y="{total_top:.1f}" width="{bar_width:.1f}" '
            f'height="{japanese_top-total_top:.1f}" fill="#f59e0b"><title>{year}年 外国人 '
            f'{foreign:,}人泊</title></rect>'
        )
        parts.append(
            f'<text x="{px:.1f}" y="{height-18}" text-anchor="middle" font-size="12" '
            f'fill="#334155">{year}年</text>'
        )
        share_points.append(f"{px:.1f},{share_y(share):.1f}")
    parts.append(
        f'<polyline points="{" ".join(share_points)}" fill="none" stroke="#0ea5e9" '
        'stroke-width="3"/>'
    )
    for index, (*_, share) in enumerate(annual):
        parts.append(
            f'<circle cx="{x(index):.1f}" cy="{share_y(share):.1f}" r="4" '
            f'fill="#0ea5e9"><title>外国人比率 {share:.1f}%</title></circle>'
        )
    parts.append(
        f'<text x="{left}" y="25" font-size="12" fill="#334155">■ 日本人　'
        '<tspan fill="#d97706">■ 外国人</tspan>　'
        '<tspan fill="#0284c7">━ 外国人比率（右軸）</tspan></text>'
    )
    for step in range(3):
        value = share_max * step / 2
        parts.append(
            f'<text x="{width-right+8}" y="{share_y(value)+4:.1f}" font-size="11" '
            f'fill="#0369a1">{value:.0f}%</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        f'aria-label="年次需要構造と外国人比率">{"".join(parts)}</svg>'
    )


def _annual_facilities_chart(history: list[dict], years: list[int]) -> str:
    """Render available December surveyed-facility counts when two or more exist."""
    annual = [
        (year, int(row["population_facilities"]))
        for year in years
        if (
            row := next(
                (
                    item
                    for item in history
                    if item["year"] == year
                    and item["month"] == 12
                    and item["population_facilities"] is not None
                ),
                None,
            )
        )
    ]
    if len(annual) < 2:
        return (
            '<p class="note">年次比較に必要な12月時点の掲載値が2年分以上ないため、'
            '施設数推移は表示していません。</p>'
        )
    width, height = 760, 340
    left, right, top, bottom = 72, 24, 48, 52
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
            f'height="{base-py:.1f}" fill="#0f766e"><title>{year}年12月 '
            f'{value:,}施設</title></rect>'
        )
        parts.append(
            f'<text x="{px:.1f}" y="{py-8:.1f}" text-anchor="middle" font-size="12" '
            f'font-weight="700" fill="#172033">{value:,}施設</text>'
        )
        parts.append(
            f'<text x="{px:.1f}" y="{height-18}" text-anchor="middle" font-size="12" '
            f'fill="#475569">{year}年</text>'
        )
    return (
        f'<svg viewBox="0 0 {width} {height}" class="chart" role="img" '
        f'aria-label="調査対象施設数の年次推移">{"".join(parts)}</svg>'
    )


def _sheet(history: list[dict]) -> str:
    latest = history[-1]
    period_label = f'{latest["year"]}年{latest["month"]}月単月（最新掲載月）'
    foreign_share = (latest["foreign_guests"] / latest["total_guests"] * 100) if latest["total_guests"] else None
    published = date.fromisoformat(latest["published_on"]).strftime("%Y/%m/%d")
    completed_year = latest["year"] if latest["month"] == 12 else latest["year"] - 1
    recent_years = list(range(completed_year - 2, completed_year + 1))
    occupancy_years = list(dict.fromkeys([2019, *recent_years]))
    facility_years = list(dict.fromkeys([2019, *recent_years]))
    body = f"""<p><a href="../index.html">← 市区町村一覧</a></p><h1>{html.escape(latest['prefecture_name'] + latest['municipality_name'])} Market Sheet</h1>
<p class="sub">{latest['year']}年{latest['month']}月 第2次速報｜データ公表日 {published}｜source ID {html.escape(latest['stat_inf_id'])}</p><p class="note">収録期間 {latest['coverage_start']}～{latest['coverage_end']}／掲載 {latest['coverage_months']}観測月</p>
<div class="cards"><div class="card"><div class="sub">客室稼働率</div><div class="metric">{_fmt(latest['occupancy_rate'], '%')}</div><span class="period-badge">{period_label}</span></div><div class="card"><div class="sub">延べ宿泊者数</div><div class="metric">{_fmt(latest['total_guests'], '人')}</div><span class="period-badge">{period_label}</span></div><div class="card"><div class="sub">外国人延べ宿泊者比率</div><div class="metric">{_fmt(foreign_share, '%')}</div><span class="period-badge">{period_label}</span></div><div class="card"><div class="sub">調査対象施設数</div><div class="metric">{_fmt(latest['population_facilities'], '施設')}</div><div class="metric-detail">回答施設数 {_fmt(latest['responding_facilities'], '施設')}</div><span class="period-badge">{period_label}</span></div></div>
<section class="panel"><h2>1. 客室稼働率</h2><p class="note">直近3年を1月〜12月の同じ軸に重ね、コロナ禍前の2019年（破線）と比較します。公式表に掲載されなかった月は線を途切れさせます。</p>{_seasonality_chart(history, 'occupancy_rate', '%', occupancy_years)}</section>
<section class="panel"><h2>2. 延べ宿泊者数（需要）</h2><p class="note">直近3年の月次需要を季節ごとに比較し、比較可能な場合は年次での日本人・外国人需要構造も確認します。</p><div class="grid-2"><div><h3>総延べ宿泊者数・月次比較（直近3年）</h3>{_seasonality_chart(history, 'total_guests', '人', recent_years)}</div><div><h3>年次需要構造と外国人比率（直近3年）</h3>{_annual_demand_chart(history, recent_years)}</div></div></section>
<section class="panel"><h2>3. 宿泊施設数（供給）</h2><p class="note">2019年および直近3年の各年12月時点を比較します。</p>{_annual_facilities_chart(history, facility_years)}<p class="note">調査対象施設数であり、客室数や実際の供給能力を示すものではありません。</p></section>
<section class="panel"><h2>4. 利用上の注意</h2><p>掲載された主な市区町村の実数であり、未回収施設を含む全市区町村の推計値ではありません。担保価値を直接示すものではなく、物件所在地の市場確認に用いる一次スクリーニング資料です。</p></section>"""
    return _document(f"{latest['municipality_name']} Market Sheet", body)


def _index(latest_rows: list[dict]) -> str:
    prefectures = sorted({row["prefecture_name"] for row in latest_rows})
    options = "".join(f'<option value="{html.escape(name)}">{html.escape(name)}</option>' for name in prefectures)

    def coverage_label(row: dict) -> str:
        warning = '<span class="warning-badge">要注意</span>' if row["coverage_months"] <= 3 else ""
        return f'{row["coverage_months"]}月{warning}'

    rows = "".join(
        f'<tr data-prefecture="{html.escape(row["prefecture_name"])}"><td data-sort="{html.escape(row["municipality_name"])}"><a href="market-sheets/{row["municipality_id"]}.html">{html.escape(row["municipality_name"])}</a></td><td class="center" data-sort="{html.escape(row["prefecture_name"])}">{html.escape(row["prefecture_name"])}</td><td class="center" data-sort="{row["coverage_end"]}">{row["coverage_end"]}</td><td class="center" data-sort="{row["coverage_months"]}">{coverage_label(row)}</td><td class="numeric" data-sort="{row["occupancy_rate"] if row["occupancy_rate"] is not None else ""}">{_fmt(row["occupancy_rate"], "%")}</td><td class="numeric" data-sort="{row["total_guests"] if row["total_guests"] is not None else ""}">{_fmt(row["total_guests"], "人")}</td><td class="numeric" data-sort="{row["population_facilities"] if row["population_facilities"] is not None else ""}">{_fmt(row["population_facilities"], "施設")}</td><td class="numeric" data-sort="{((row["foreign_guests"] / row["total_guests"] * 100) if row["total_guests"] else "")}">{_fmt((row["foreign_guests"] / row["total_guests"] * 100) if row["total_guests"] else None, "%")}</td></tr>'
        for row in latest_rows
    )
    body = f"""<p><a href="../index.html">← 全国 Hotel Market Monitor</a></p><h1>Municipality Hotel Market Monitor</h1><p class="sub">月次第2次速報から、担保物件所在地の市区町村市況を確認します。掲載自治体のみを対象とします。</p>
<section class="panel"><h2>市区町村一覧</h2><p class="note">各自治体の最新掲載月の値です。掲載条件により最新月や収録月数が異なります。掲載3か月以下は単月ノイズに注意が必要です。</p><div class="tools"><select id="prefecture"><option value="">全都道府県</option>{options}</select><input id="search" type="search" placeholder="市区町村名を検索"><span id="count">{len(latest_rows)}件</span></div><div class="scroll"><table id="markets"><thead><tr><th rowspan="2" class="sortable"><button data-column="0" data-type="text">市区町村</button></th><th colspan="3" class="th-group th-meta">自治体属性</th><th colspan="3" class="th-group th-supply-demand">需給</th><th colspan="1" class="th-group th-inbound">インバウンド</th></tr><tr><th class="sortable center"><button data-column="1" data-type="text">都道府県</button></th><th class="sortable center"><button data-column="2" data-type="text">最新掲載月</button></th><th class="sortable center"><button data-column="3" data-type="number">掲載月数</button></th><th class="sortable numeric"><button data-column="4" data-type="number">客室稼働率</button></th><th class="sortable numeric"><button data-column="5" data-type="number">延べ宿泊者数</button></th><th class="sortable numeric"><button data-column="6" data-type="number">調査対象施設数</button></th><th class="sortable numeric"><button data-column="7" data-type="number">外国人比率</button></th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="panel"><h2>利用上の注意</h2><p>市区町村値と都道府県値は集計基準が異なります。市区町村値を合計して都道府県値を再構成することはできません。2026年1月から施設規模の層化基準が従業者数から客室数へ変更されています。</p></section>
<script>(()=>{{const table=document.querySelector('#markets'),body=table.tBodies[0],q=document.querySelector('#search'),p=document.querySelector('#prefecture'),count=document.querySelector('#count');let active=-1,direction=1;function update(){{const text=q.value.trim().toLocaleLowerCase('ja');let visible=0;[...body.rows].forEach(row=>{{const show=(!p.value||row.dataset.prefecture===p.value)&&row.cells[0].textContent.toLocaleLowerCase('ja').includes(text);row.hidden=!show;if(show)visible++;}});count.textContent=visible+'件';}}q.addEventListener('input',update);p.addEventListener('change',update);table.querySelectorAll('button[data-column]').forEach(button=>button.addEventListener('click',()=>{{const column=Number(button.dataset.column),type=button.dataset.type;direction=active===column?-direction:1;active=column;table.querySelectorAll('button[data-column]').forEach(item=>item.removeAttribute('data-direction'));button.dataset.direction=direction===1?'asc':'desc';const sorted=[...body.rows].sort((a,b)=>{{const av=a.cells[column].dataset.sort??'',bv=b.cells[column].dataset.sort??'';const aMissing=av==='',bMissing=bv==='';if(aMissing!==bMissing)return aMissing?1:-1;if(aMissing)return 0;const result=type==='number'?Number(av)-Number(bv):av.localeCompare(bv,'ja');return result*direction;}});sorted.forEach(row=>body.appendChild(row));update();}}));}})();</script>"""
    return _document("Municipality Hotel Market Monitor", body)


def generate_municipality_reports(database: Path, output_dir: Path) -> dict:
    """Write municipality index and one Market Sheet per municipality."""
    latest, histories = _load(database)
    if not latest:
        raise ValueError("municipality market data is empty")
    sheets = output_dir / "market-sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    (output_dir / "index.html").write_text(_index(latest), encoding="utf-8")
    for row in latest:
        (sheets / f'{row["municipality_id"]}.html').write_text(
            _sheet(histories[row["municipality_id"]]), encoding="utf-8"
        )
    metadata = {"municipalities": len(latest), "periods": sorted({f'{row["year"]}-{row["month"]:02d}' for history in histories.values() for row in history})}
    (output_dir / "report-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"report": str(output_dir / "index.html"), "market_sheets": len(latest), **metadata}
