"""Render portable CSV and static HTML market-monitoring reports."""

from __future__ import annotations

import csv
import html
import json
import os
import sqlite3
from pathlib import Path

from .analysis import AnalysisConfig, analyze_database, config_as_dict


CSV_FIELDS = [
    "prefecture_code", "prefecture_name", "target_year", "target_month", "base_year", "release_type",
    "total_guests", "average_occupancy_rate", "average_facilities", "foreign_share_pct",
    "demand_vs_base_pct", "demand_ltm_yoy_pct", "foreign_ltm_yoy_pct",
    "occupancy_ltm_yoy_pp", "facility_ltm_yoy_pct", "foreign_share_yoy_pp",
    "recent_demand_yoy_pct", "recent_occupancy_yoy_pp", "monthly_cv", "peak_month_share_pct",
    "seasonal_occupancy_cv", "seasonal_occupancy_cv_percentile",
    "seasonal_occupancy_cv_relative", "top3_demand_share_pct",
    "top3_demand_share_pct_percentile", "top3_demand_share_pct_relative",
    "demand_ltm_yoy_pct_percentile", "demand_ltm_yoy_pct_relative",
    "foreign_share_pct_percentile", "foreign_share_pct_relative",
    "facility_ltm_yoy_pct_percentile", "facility_ltm_yoy_pct_relative",
    "recent_demand_yoy_pct_percentile", "recent_demand_yoy_pct_relative",
    "recovery_direction", "demand_mix_direction", "momentum_direction",
    "supply_demand_direction", "market_state", "market_characteristics", "is_watch",
    "signals", "watch_reasons",
    "observed_fact", "interpretation", "next_action", "data_quality_note",
]


def _source_as_of(database: Path) -> str:
    connection = sqlite3.connect(database)
    try:
        value = connection.execute("SELECT MAX(retrieved_at) FROM source_files").fetchone()[0]
    finally:
        connection.close()
    return value or "unknown"


def _serializable(row: dict) -> dict:
    result = {key: row.get(key) for key in CSV_FIELDS}
    result["market_characteristics"] = " / ".join(row["market_characteristics"])
    result["signals"] = " / ".join(row["signals"])
    result["watch_reasons"] = " / ".join(row["watch_reasons"])
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
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root{{--ink:#172033;--muted:#637083;--line:#dce2ea;--paper:#fff;--bg:#f3f6f9;--watch:#a73b27;--accent:#155e75}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.55}}
main{{max-width:1180px;margin:auto;padding:32px 20px 64px}}h1{{font-size:2rem;margin:.2rem 0}}h2{{margin-top:2rem}}.sub{{color:var(--muted)}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:22px 0}}.card,.panel{{background:var(--paper);border:1px solid var(--line);border-radius:10px;padding:16px}}
.metric{{font-size:1.45rem;font-weight:700}}table{{width:100%;border-collapse:collapse;background:var(--paper);font-size:.9rem}}th,td{{padding:9px;border:1px solid var(--line);text-align:left}}th{{background:#eaf0f5}}tr.watch td:first-child{{border-left:4px solid var(--watch)}}
.tag{{display:inline-block;border-radius:999px;padding:2px 9px;background:#e4f1f5;color:var(--accent);font-size:.8rem}}a{{color:#075985}}.scroll{{overflow-x:auto}}ul{{padding-left:1.2rem}}
.bars{{height:180px;display:flex;align-items:flex-end;gap:5px;border-bottom:1px solid var(--line);padding-top:16px}}.stack{{flex:1;min-height:2px;position:relative;display:flex;flex-direction:column;justify-content:flex-end}}.stack span{{position:absolute;top:100%;width:100%;text-align:center;font-size:.7rem;color:var(--muted);padding-top:3px}}.domestic{{background:#3c8296}}.foreign{{background:#e19745}}.legend{{display:flex;gap:18px;margin-top:28px;font-size:.85rem;color:var(--muted)}}.swatch{{display:inline-block;width:10px;height:10px;margin-right:5px}}
@media print{{body{{background:#fff}}main{{max-width:none}}.panel,.card{{break-inside:avoid}}}}
</style></head><body><main>{body}</main></body></html>"""


def _demand_mix_chart(
    totals: list[float], japanese: list[float | None], foreign: list[float | None], labels: list[str]
) -> str:
    maximum = max(totals) if totals else 0
    bars = []
    for total, domestic, inbound, label in zip(totals, japanese, foreign, labels, strict=True):
        domestic_value = domestic or 0
        inbound_value = inbound or 0
        domestic_share = domestic_value / total * 100 if total else 0
        inbound_share = inbound_value / total * 100 if total else 0
        bars.append(
            f'<div class="stack" style="height:{(total / maximum * 100) if maximum else 0:.1f}%" '
            f'title="{label}: 日本人 {domestic_value:,.0f}／外国人 {inbound_value:,.0f}">'
            f'<div class="foreign" style="height:{inbound_share:.1f}%"></div>'
            f'<div class="domestic" style="height:{domestic_share:.1f}%"></div>'
            f'<span>{html.escape(label[-2:])}</span></div>'
        )
    return (
        '<div class="bars" role="img" aria-label="月別日本人・外国人延べ宿泊者数">'
        + "".join(bars)
        + '</div><div class="legend"><span><i class="swatch domestic"></i>日本人</span>'
        '<span><i class="swatch foreign"></i>外国人</span></div>'
    )


def _market_sheet(row: dict, as_of: str) -> str:
    reasons = "".join(f"<li>{html.escape(reason)}</li>" for reason in row["watch_reasons"]) or "<li>追加調査トリガーへの該当なし</li>"
    signals = "".join(f"<li>{html.escape(signal)}</li>" for signal in row["signals"]) or "<li>方向シグナルなし</li>"
    characteristics = "".join(
        f"<li>{html.escape(item)}</li>" for item in row["market_characteristics"]
    ) or "<li>顕著な季節特性タグなし</li>"
    cards = [
        (f"Recovery {row['recovery_direction']}", _fmt(row["demand_vs_base_pct"], "%")),
        (f"Demand Mix {row['demand_mix_direction']}", _fmt(row["foreign_share_pct"], "%")),
        (f"Momentum {row['momentum_direction']}", _fmt(row["demand_ltm_yoy_pct"], "%")),
        (f"Supply-Demand {row['supply_demand_direction']}", _fmt(row["occupancy_ltm_yoy_pp"], "pt")),
        (f"直近{row['recent_months']}か月YoY", _fmt(row["recent_demand_yoy_pct"], "%")),
        ("施設数LTM YoY", _fmt(row["facility_ltm_yoy_pct"], "%")),
        (
            f"Seasonal CV（{row['seasonal_occupancy_cv_relative']}）",
            f"{row['seasonal_occupancy_cv']:.3f}",
        ),
        (
            f"上位3か月集中度（{row['top3_demand_share_pct_relative']}）",
            _fmt(row["top3_demand_share_pct"], "%"),
        ),
    ]
    card_html = "".join(f'<div class="card"><div class="sub">{label}</div><div class="metric">{value}</div></div>' for label, value in cards)
    body = f"""<a href="../index.html">← 全体レポート</a><h1>{html.escape(row['prefecture_name'])} マーケットシート</h1>
<p class="sub">基準月 {row['target_year']}年{row['target_month']}月／LTM／公表区分 {row['release_type']}／データ取得基準 {html.escape(as_of)}</p>
<p><span class="tag">{html.escape(row['market_state'])}</span></p><div class="cards">{card_html}</div>
<section class="panel"><h2>LTM月別需要構成</h2>{_demand_mix_chart(row['monthly_total_guests'], row['monthly_japanese_guests'], row['monthly_foreign_guests'], row['monthly_labels'])}<h2>観測事実</h2><p>{html.escape(row['observed_fact'])}</p><h2>シグナル</h2><ul>{signals}</ul><h2>市場特性</h2><ul>{characteristics}</ul><h2>追加調査トリガー</h2><ul>{reasons}</ul></section>
<section class="panel"><h2>解釈上の注意</h2><p>{html.escape(row['interpretation'])}</p><h2>次の確認事項</h2><p>{html.escape(row['next_action'])}</p></section>"""
    return _document(f"{row['prefecture_name']} マーケットシート", body)


def _index_html(rows: list[dict], config: AnalysisConfig, as_of: str) -> str:
    watches = [row for row in rows if row["is_watch"]]
    states: dict[str, int] = {}
    for row in rows:
        states[row["market_state"]] = states.get(row["market_state"], 0) + 1
    state_list = "".join(f"<li>{html.escape(key)}: {value}県</li>" for key, value in sorted(states.items()))
    table_rows = "".join(
        f'<tr class="{"watch" if row["is_watch"] else ""}"><td><a href="market-sheets/{row["prefecture_code"]:02}.html">{html.escape(row["prefecture_name"])}</a></td>'
        f'<td>{html.escape(row["market_state"])}</td><td>{_fmt(row["demand_vs_base_pct"], "%")}</td><td>{_fmt(row["demand_ltm_yoy_pct"], "%")}<br><small>{html.escape(row["demand_ltm_yoy_pct_relative"])}</small></td>'
        f'<td>{_fmt(row["recent_demand_yoy_pct"], "%")}</td><td>{_fmt(row["occupancy_ltm_yoy_pp"], "pt")}</td><td>{_fmt(row["facility_ltm_yoy_pct"], "%")}</td><td>{html.escape(" / ".join(row["market_characteristics"]) or "—")}</td><td>{html.escape(" / ".join(row["watch_reasons"]) or "—")}</td></tr>'
        for row in rows
    )
    body = f"""<h1>宿泊市場モニタリング</h1><p class="sub">基準月 {config.target_year}年{config.target_month}月／LTM／基準年 {config.base_year}年／データ取得基準 {html.escape(as_of)}</p>
<div class="cards"><div class="card"><div class="sub">分析対象</div><div class="metric">47都道府県</div></div><div class="card"><div class="sub">ウォッチ対象</div><div class="metric">{len(watches)}県</div></div><div class="card"><div class="sub">公表区分</div><div class="metric">確定値</div></div></div>
<section class="panel"><h2>市場状態の分布</h2><ul>{state_list}</ul><p>ウォッチ判定は担保価値や融資可否の判定ではなく、個別ホテルと商圏について追加調査するための一次スクリーニングです。</p></section>
<h2>都道府県別結果</h2><div class="scroll"><table><thead><tr><th>都道府県</th><th>市場状態</th><th>{config.base_year}年LTM比</th><th>LTM YoY・相対位置</th><th>直近{config.recent_months}か月YoY</th><th>稼働率LTM前年差</th><th>施設数LTM YoY</th><th>季節特性</th><th>追加調査トリガー</th></tr></thead><tbody>{table_rows}</tbody></table></div>"""
    return _document("宿泊市場モニタリング", body)


def generate_reports(database: Path, output_dir: Path, config: AnalysisConfig) -> dict:
    rows = analyze_database(database, config)
    output_dir.mkdir(parents=True, exist_ok=True)
    sheets = output_dir / "market-sheets"
    sheets.mkdir(exist_ok=True)
    as_of = _source_as_of(database)
    _write_csv(output_dir / "prefecture-market.csv", rows)
    watches = [row for row in rows if row["is_watch"]]
    _write_csv(output_dir / "watchlist.csv", watches)
    (output_dir / "index.html").write_text(_index_html(rows, config, as_of), encoding="utf-8")
    for row in rows:
        (sheets / f"{row['prefecture_code']:02}.html").write_text(_market_sheet(row, as_of), encoding="utf-8")
    metadata = {"source_as_of": as_of, "rows": len(rows), "watch_count": len(watches), "config": config_as_dict(config)}
    (output_dir / "report-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"report": str(output_dir / "index.html"), "market_sheets": len(rows), "watch_count": len(watches)}
