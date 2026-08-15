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
.review{{display:flex;flex-wrap:wrap;gap:6px 18px;border:1px solid #d97706;background:#fff7ed;color:#9a3412;border-radius:10px;padding:8px 12px;margin-bottom:14px;font-size:.82rem;font-weight:600}}
.cards{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:22px 0}}.card,.panel{{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:16px}}.metric{{font-size:1.45rem;font-weight:700}}.metric-detail{{font-size:.8rem;color:var(--muted)}}
.panel{{margin-top:18px}}.grid-2{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}.scroll{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:#fff;font-size:.9rem}}th,td{{padding:9px;border:1px solid var(--line);text-align:left}}th{{background:#eaf0f5}}.numeric{{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}}
.tools{{display:flex;gap:12px;align-items:center;margin:12px 0}}input,select{{border:1px solid #aeb8c5;border-radius:7px;padding:9px 11px;font:inherit;background:#fff}}input{{flex:1}}.chart{{width:100%;height:auto;display:block}}.period-badge{{display:inline-block;border-radius:999px;background:#e0f2fe;color:#075985;padding:2px 7px;margin-top:5px;font-size:.72rem;font-weight:700}}.warning-badge{{display:inline-block;border-radius:999px;background:#fff1f2;color:#be123c;border:1px solid #fecdd3;padding:1px 6px;margin-left:5px;font-size:.7rem;font-weight:700}}.sortable button{{width:100%;border:0;background:transparent;padding:0;color:inherit;font:inherit;font-weight:700;text-align:left;cursor:pointer;white-space:nowrap}}.sortable.numeric button{{text-align:right}}.sortable button::after{{content:" ↕";color:#64748b}}.sortable button[data-direction="asc"]::after{{content:" ↑"}}.sortable button[data-direction="desc"]::after{{content:" ↓"}}
@media(min-width:760px){{.cards{{grid-template-columns:repeat(4,minmax(0,1fr))}}}}@media(max-width:760px){{.grid-2{{grid-template-columns:1fr}}}}
</style></head><body><main><div class="review"><span>レビュー前・暫定版：集計ロジックと生成結果は未レビューです。</span><span>制度変更：2026年1月から層化基準が従業者数から客室数へ変更されています。</span></div>{body}</main></body></html>"""


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
        classes = connection.execute(
            """SELECT f.*,m.municipality_name
               FROM monthly_municipality_market AS f
               JOIN municipalities AS m ON m.id=f.municipality_id
               ORDER BY f.municipality_id,f.year,f.month,
                 CASE f.room_size_class
                   WHEN 'total' THEN 0 WHEN '1_to_9' THEN 1
                   WHEN '10_to_19' THEN 2 WHEN '20_plus' THEN 3 END"""
        ).fetchall()
    finally:
        connection.close()
    histories: dict[int, list[dict]] = {}
    for row in rows:
        histories.setdefault(row["municipality_id"], []).append(dict(row))
    class_rows: dict[tuple[int, int, int], list[dict]] = {}
    for row in classes:
        class_rows.setdefault((row["municipality_id"], row["year"], row["month"]), []).append(dict(row))
    for history in histories.values():
        for row in history:
            row["classes"] = class_rows[(row["municipality_id"], row["year"], row["month"])]
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


def _sheet(history: list[dict]) -> str:
    latest = history[-1]
    latest_index = latest["year"] * 12 + latest["month"] - 1
    chart_history = [
        row
        for row in history
        if row["year"] * 12 + row["month"] - 1 >= latest_index - 35
    ]
    period_label = f'{latest["year"]}年{latest["month"]}月単月（最新掲載月）'
    foreign_share = (latest["foreign_guests"] / latest["total_guests"] * 100) if latest["total_guests"] else None
    published = date.fromisoformat(latest["published_on"]).strftime("%Y/%m/%d")
    room_labels = {"total": "総数", "1_to_9": "1～9室", "10_to_19": "10～19室", "20_plus": "20室以上"}
    class_body = "".join(
        f'<tr><td>{room_labels[row["room_size_class"]]}</td><td class="numeric">{_fmt(row["total_guests"], "人")}</td><td class="numeric">{_fmt(row["foreign_guests"], "人")}</td><td class="numeric">{_fmt(row["occupancy_rate"], "%")}</td><td class="numeric">{_fmt(row["responding_facilities"], "施設")}</td></tr>'
        for row in latest["classes"]
    )
    body = f"""<p><a href="../index.html">← 市区町村一覧</a></p><h1>{html.escape(latest['prefecture_name'] + latest['municipality_name'])} Market Sheet</h1>
<p class="sub">{latest['year']}年{latest['month']}月 第2次速報｜データ公表日 {published}｜source ID {html.escape(latest['stat_inf_id'])}</p><p class="note">収録期間 {latest['coverage_start']}～{latest['coverage_end']}／掲載 {latest['coverage_months']}観測月</p>
<div class="cards"><div class="card"><div class="sub">客室稼働率</div><div class="metric">{_fmt(latest['occupancy_rate'], '%')}</div><span class="period-badge">{period_label}</span></div><div class="card"><div class="sub">延べ宿泊者数</div><div class="metric">{_fmt(latest['total_guests'], '人')}</div><span class="period-badge">{period_label}</span></div><div class="card"><div class="sub">外国人延べ宿泊者比率</div><div class="metric">{_fmt(foreign_share, '%')}</div><span class="period-badge">{period_label}</span></div><div class="card"><div class="sub">調査対象施設数</div><div class="metric">{_fmt(latest['population_facilities'], '施設')}</div><div class="metric-detail">回答施設数 {_fmt(latest['responding_facilities'], '施設')}</div><span class="period-badge">{period_label}</span></div></div>
<section class="panel"><h2>月次推移</h2><p class="note">直近36暦月を表示します。公式表に掲載されなかった月は線を途切れさせます。</p><div class="grid-2"><div><h3>延べ宿泊者数</h3>{_line_chart(chart_history, 'total_guests', '人', '#2563eb')}</div><div><h3>客室稼働率</h3>{_line_chart(chart_history, 'occupancy_rate', '%', '#0f766e')}</div></div></section>
<section class="panel"><h2>客室規模別内訳</h2><p class="note">区分ごとに10施設以上の回答がない場合は非表章（—）です。</p><div class="scroll"><table><thead><tr><th>客室区分</th><th>延べ宿泊者数</th><th>外国人延べ宿泊者数</th><th>客室稼働率</th><th>回答施設数</th></tr></thead><tbody>{class_body}</tbody></table></div></section>
<section class="panel"><h2>利用上の注意</h2><p>掲載された主な市区町村の実数であり、未回収施設を含む全市区町村の推計値ではありません。担保価値を直接示すものではなく、物件所在地の市場確認に用いる一次スクリーニング資料です。</p></section>"""
    return _document(f"{latest['municipality_name']} Market Sheet", body)


def _index(latest_rows: list[dict]) -> str:
    prefectures = sorted({row["prefecture_name"] for row in latest_rows})
    options = "".join(f'<option value="{html.escape(name)}">{html.escape(name)}</option>' for name in prefectures)

    def coverage_label(row: dict) -> str:
        warning = '<span class="warning-badge">要注意</span>' if row["coverage_months"] <= 3 else ""
        return f'{row["coverage_months"]}月{warning}'

    rows = "".join(
        f'<tr data-prefecture="{html.escape(row["prefecture_name"])}"><td data-sort="{html.escape(row["municipality_name"])}"><a href="market-sheets/{row["municipality_id"]}.html">{html.escape(row["municipality_name"])}</a></td><td data-sort="{html.escape(row["prefecture_name"])}">{html.escape(row["prefecture_name"])}</td><td class="numeric" data-sort="{row["coverage_end"]}">{row["coverage_end"]}</td><td class="numeric" data-sort="{row["coverage_months"]}">{coverage_label(row)}</td><td class="numeric" data-sort="{row["occupancy_rate"] if row["occupancy_rate"] is not None else ""}">{_fmt(row["occupancy_rate"], "%")}</td><td class="numeric" data-sort="{row["total_guests"] if row["total_guests"] is not None else ""}">{_fmt(row["total_guests"], "人")}</td><td class="numeric" data-sort="{((row["foreign_guests"] / row["total_guests"] * 100) if row["total_guests"] else "")}">{_fmt((row["foreign_guests"] / row["total_guests"] * 100) if row["total_guests"] else None, "%")}</td><td class="numeric" data-sort="{row["population_facilities"] if row["population_facilities"] is not None else ""}">{_fmt(row["population_facilities"], "施設")}</td></tr>'
        for row in latest_rows
    )
    body = f"""<p><a href="../index.html">← 全国 Hotel Market Monitor</a></p><h1>Municipality Hotel Market Monitor</h1><p class="sub">月次第2次速報から、担保物件所在地の市区町村市況を確認します。掲載自治体のみを対象とします。</p>
<section class="panel"><h2>市区町村一覧</h2><p class="note">各自治体の最新掲載月の値です。掲載条件により最新月や収録月数が異なります。掲載3か月以下は単月ノイズに注意が必要です。</p><div class="tools"><select id="prefecture"><option value="">全都道府県</option>{options}</select><input id="search" type="search" placeholder="市区町村名を検索"><span id="count">{len(latest_rows)}件</span></div><div class="scroll"><table id="markets"><thead><tr><th class="sortable"><button data-column="0" data-type="text">市区町村</button></th><th class="sortable"><button data-column="1" data-type="text">都道府県</button></th><th class="sortable numeric"><button data-column="2" data-type="text">最新掲載月</button></th><th class="sortable numeric"><button data-column="3" data-type="number">掲載月数</button></th><th class="sortable numeric"><button data-column="4" data-type="number">客室稼働率</button></th><th class="sortable numeric"><button data-column="5" data-type="number">延べ宿泊者数</button></th><th class="sortable numeric"><button data-column="6" data-type="number">外国人比率</button></th><th class="sortable numeric"><button data-column="7" data-type="number">調査対象施設数</button></th></tr></thead><tbody>{rows}</tbody></table></div></section>
<section class="panel"><h2>利用上の注意</h2><p>市区町村値と都道府県値は集計基準が異なります。市区町村値を合計して都道府県値を再構成することはできません。</p></section>
<script>(()=>{{const table=document.querySelector('#markets'),body=table.tBodies[0],q=document.querySelector('#search'),p=document.querySelector('#prefecture'),count=document.querySelector('#count');let active=-1,direction=1;function update(){{const text=q.value.trim().toLocaleLowerCase('ja');let visible=0;[...body.rows].forEach(row=>{{const show=(!p.value||row.dataset.prefecture===p.value)&&row.cells[0].textContent.toLocaleLowerCase('ja').includes(text);row.hidden=!show;if(show)visible++;}});count.textContent=visible+'件';}}q.addEventListener('input',update);p.addEventListener('change',update);table.querySelectorAll('button[data-column]').forEach(button=>button.addEventListener('click',()=>{{const column=Number(button.dataset.column),type=button.dataset.type;direction=active===column?-direction:1;active=column;table.querySelectorAll('button[data-column]').forEach(item=>item.removeAttribute('data-direction'));button.dataset.direction=direction===1?'asc':'desc';const sorted=[...body.rows].sort((a,b)=>{{const av=a.cells[column].dataset.sort??'',bv=b.cells[column].dataset.sort??'';if(av===''&&bv!=='')return 1;if(bv===''&&av!=='')return -1;const result=type==='number'?Number(av)-Number(bv):av.localeCompare(bv,'ja');return result*direction;}});sorted.forEach(row=>body.appendChild(row));update();}}));}})();</script>"""
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
