# Hotel Supply & Demand ETL

観光庁「宿泊旅行統計調査」の公式Excelを取得・正規化し、SQLiteと静的HTMLレポートを再生成するデータパイプラインです。

**[Live Demo：ホテルマーケットレポート](https://saito-mmn.github.io/hotel-supply-demand-etl/)**

[![CI](https://github.com/saito-mmn/hotel-supply-demand-etl/actions/workflows/ci.yml/badge.svg)](https://github.com/saito-mmn/hotel-supply-demand-etl/actions/workflows/ci.yml)
[![Update and deploy](https://github.com/saito-mmn/hotel-supply-demand-etl/actions/workflows/update-and-deploy.yml/badge.svg)](https://github.com/saito-mmn/hotel-supply-demand-etl/actions/workflows/update-and-deploy.yml)

## Why — 解決する業務課題

銀行でホテル担保評価を担当する中で、物件単体の収益性だけでなく、所在地の宿泊需要、客室稼働率、供給環境などの市場動向を継続的に確認する必要がありました。

一方で、観光庁の宿泊統計は複数のExcelに分かれており、年度や公表区分によって帳票構造も異なります。特に市区町村データは月次ファイルの複数表に分散しているため、分析のたびに取得・加工・照合を行う必要がありました。

そこで、**分析者が毎回データを集め直すのではなく、公式データを継続的に取得・検証・再利用できる状態を作ること**を目的として本プロジェクトを開発しました。

## What — 何を提供するか

観光庁・e-Statの「宿泊旅行統計調査」から、全国・都道府県・市区町村の宿泊市場データを共通形式へ整備し、評価担当者が市場環境を段階的に確認できるMarket Reportを生成します。

主な確認項目は以下です。

- 宿泊需要
- 客室稼働率
- 外国人宿泊者比率
- 調査対象施設数
- 季節変動・需給動向

本プロジェクトは担保価値や融資可否を自動判定するものではありません。

**市場データを継続的かつ比較可能な形で提供し、個別物件について追加調査すべき論点を把握するための一次スクリーニング資料を提供すること**を目的としています。

## How — どう実現するか

```text
e-Stat / 観光庁
      │  年確定値・月次第2次速報 Excel
      ▼
Source discovery ── 採用ソース設定
      ▼
Fetcher ─────────── manifest・取得日時・SHA-256
      ▼
Parser ──────────── 月次レコードへ正規化
      ▼
Validation ──────── キー・件数・値範囲・内訳を検証
      ▼
SQLite ──────────── 出典・マスター・月次ファクト
      ▼
Static report ───── 全国 → 都道府県 → 市区町村
      ▼
GitHub Actions ──── CI・更新・GitHub Pages配信

```

## Technical Highlights

- 年度・公表月ごとに構造が異なる公式Excelを、都道府県・市区町村別の共通スキーマへ正規化
- `statInfId`、URL、公表日、取得日時、SHA-256を記録し、採用ソースと訂正履歴を追跡
- 一時ファイル・一時DB・一時レポートを検証後に原子的に切り替え、失敗時は既存成果物を保持
- fixtureベースのCIと公式サイトへアクセスする更新Workflowを分離し、品質ゲート通過時のみGitHub Pagesへ反映
- 全国・47都道府県・307市区町村の静的レポートをSQLiteから自動生成

## データソース

観光庁「宿泊旅行統計調査」の公式Excelを使用しています。

- **都道府県**：年確定値。全国・47都道府県の需要、客室稼働率、施設数を収録
- **市区町村**：月次第2次速報。公式表に掲載された主な市区町村の需要、客室稼働率、施設数を収録

[観光庁 宿泊旅行統計調査](https://www.mlit.go.jp/kankocho/tokei_hakusyo/shukuhakutokei.html) /
[e-Stat 宿泊旅行統計調査](https://www.e-stat.go.jp/stat-search/database?layout=datalist&toukei=00601020)

集計基準、対象期間、欠損の扱いは[分析方法・指標・データ上の制約](docs/methodology.md)を参照してください。

## 技術スタック

- Python 3.11 / openpyxl
- SQLite
- HTML / CSS / JavaScript
- TOML / JSON
- pytest / Ruff / mypy
- GitHub Actions / GitHub Pages

## 設計上の重要判断

1. **APIではなく公式Excelを入力にする**：対象期間・指標がe-Stat統計値APIで一貫して提供されていないため、原Excelを正式な入力としました。
2. **都道府県と市区町村を別ファクトとして保持する**：推計を含む都道府県値と、掲載・回収基準のある市区町村実数を混在させず、出典と集計基準を保持します。
3. **来歴管理と安全な更新を組み込む**：採用ソースを設定としてレビュー可能にし、取得結果のハッシュを記録します。更新は一時DB・レポートの品質検証後に反映します。

## Quick Start

Python 3.11以上が必要です。Excelパイプラインにe-Stat APIのアプリケーションIDは不要です。

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/hotel-etl pipeline
.venv/bin/hotel-etl municipality-pipeline --base-year 2019
```

```bash
.venv/bin/python -m pytest
```

部分実行コマンドは`hotel-etl --help`を参照してください。

## Documentation

### 公表データ

- [分析方法・指標・データ上の制約](docs/methodology.md)
- [市区町村データの収録状況](docs/municipality-source-coverage.md)
- [e-Stat API提供範囲調査](docs/estat-api-audit.md)

### SQLite

- [SQLiteデータモデル・ER図](docs/data-model.md)
- [データ辞書](docs/data-dictionary.md)

### データ更新・運用

- [公式データ更新パイプライン](docs/update-pipeline.md)
- [GitHub Pages・自動更新運用](docs/deployment.md)

## License

[MIT License](LICENSE)
