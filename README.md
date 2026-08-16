# Hotel Supply & Demand ETL

> [!IMPORTANT]
> 年確定値による全国・都道府県マクロ分析と、月次第2次速報による市区町村ローカル市場分析を、同じリポジトリ内の独立したデータパイプラインとして扱います。

## このプロジェクトで解決する業務課題

ホテルの担保評価では、全国や都道府県の市場環境だけでなく、担保物件が所在する市区町村の宿泊需要・客室稼働率を継続的に確認する必要があります。
特に市区町村値は、e-Statで月ごとに配布される第2次速報Excelを個別に開き、複数の参考表を横断して集計する必要があり、実務上の負担が大きい作業です。

本プロジェクトは、次の二つの粒度を分離して自動化します。

| ドメイン | 入力 | 粒度・更新頻度 | 主な用途 |
|---|---|---|---|
| `prefecture` | 観光庁の年確定値Excel | 全国・47都道府県／年次 | ホテル市場の地合いと都道府県マクロ環境の把握 |
| `municipality` | e-Statの第2次速報Excel | 主な市区町村／月次 | 担保所在地の需要・稼働率時系列の確認 |

市区町村値は全市区町村の完全な統計ではありません。
公式Excelに掲載される「主な市区町村」のうち、市区町村別・客室区分別に10施設以上の回収があった区分の実数です。未回収分を推定した都道府県値とは集計基準が異なるため、市区町村値の合計から都道府県値を再構成しません。

## 方針

観光庁「宿泊旅行統計調査」はe-Statと観光庁から公式Excelが配布され、一部の旧系列はe-Stat APIからも取得できます。継続利用には、年度別の提供形式、速報値と確定値、訂正・差し替え、欠損、データ品質を管理する必要があります。

API提供範囲を実測した結果、2019・2024・2025年の年確定値は統計値APIの対象として確認できませんでした。そのため、2019～2025年MVPは公式Excelを入力とし、属人的なNotebook処理を、公式データの取得から検証、蓄積、分析用データ生成、レポート出力まで再実行できるデータパイプラインへ移行します。

### 利用目的

担保評価・審査・与信管理の担当者が、全国から担保所在地まで段階的に市場を確認し、評価前提や個別ホテルの実績について追加確認が必要な変化を把握することを目的とします。

```text
全国のホテル市況
    ↓
都道府県の需要構造・稼働率・季節性
    ↓
担保所在地である市区町村の月次需要・客室稼働率
    ↓
個別ホテルのADR・RevPAR・GOP・競合状況を追加調査
```

本システムは担保価値、融資可否、LTV、個別ホテルの収益性を自動算定するものではありません。統計加工と比較作業を自動化し、評価担当者が追加調査すべき市場と期間を確認するための補助資料を生成します。

### 技術的な取り組み

- TOMLで固定した公式Excelの取得と、URL・公表日・取得日時・SHA-256による来歴管理
- 年度や公表月で構造の異なるExcelを共通の月次レコードへ正規化するparser
- 都道府県・市区町村・客室規模区分・欠測・値範囲・内訳整合性のデータ品質検証
- 出典、マスター、都道府県ファクト、市区町村ファクトを分離したSQLiteデータモデル
- 一時DBの原子的置換と対象月のトランザクション置換による、失敗時に既存データを壊さないDB更新
- 取得からDB生成・静的HTMLレポートまでの一括実行と、各工程の個別再実行を選べるCLI
- fixtureを用いたparser・品質検証・SQLiteロード・レポート生成の自動テスト
- 全国・都道府県・市区町村へドリルダウンする静的HTMLレポート

この再構築を通じて、外部の非構造データを取得・正規化するだけでなく、出典、版、品質、再実行性、下流利用まで考慮した小規模データパイプラインの設計・実装を目指します。

### 自動化範囲の設計判断

年確定値は更新頻度が低く、MVPの対象ファイル数も限定されます。そのため、都道府県側はレビュー可能な`sources.toml`に取得対象URLを明示します。市区町村側も初期版では公式一覧ページを実行時にスクレイピングせず、`municipality_sources.toml`へ提供元、調査年月、公表日、source ID、原ExcelのURLを固定します。いずれも取得時にXLSX形式、SHA-256、取得履歴を検証する方針です。

公式ページからのリンク自動発見、速報値の定期取得、GitHub Actionsによる巡回、自動PRは、継続運用の必要性が確認された場合のOptional機能とします。低頻度・少数ファイルのために複雑な収集基盤を先に作らず、ETL本体、品質検証、再現性を優先します。

e-Stat APIの実測結果は [e-Stat API 提供範囲調査](docs/estat-api-audit.md) に記録しています。

## 現在の状態

都道府県側は、2019～2025年の年確定値Excelについて、取得、manifest・SHA-256による来歴管理、SQLite再生成、全国ダッシュボード、47都道府県Market Sheetまで実装済みです。分析ロジックとレポートは暫定版でありレビュー前です。

市区町村側は、公式原Excelを固定する`municipality_sources.toml`、取得・manifest・SHA-256管理、月次共通レコードモデル、参考第5・6・8・11・12表を結合するparser、品質検証、SQLiteロード、専用CLI、市区町村一覧と月次Market Sheetを実装しました。都道府県側と比較期間を合わせ、2019年1月～2026年5月の連続89か月、72,688レコード、307自治体を収録しています。原則はe-Statを利用し、e-Statから原Excelリンクを確認できない2026年1月のみ観光庁公式Excelを採用します。parserは都道府県名と市区町村名を分離し、総数・1～9室・10～19室・20室以上を別レコードとして保持します。レポートと集計ロジックは暫定版でありレビュー前です。月別の掲載状況、例外ソース、公式表の値・掲載差異、2026年1月からの層化基準変更は[市区町村第2次速報 ソース収録状況](docs/municipality-source-coverage.md)に記録しています。

### 処理フローとモジュール構成

都道府県と市区町村は、対象粒度とExcel形式は異なりますが、どちらも同じETLフローで処理します。`cli.py`がコマンドを受け付け、各`pipeline.py`が処理順序を制御し、取得・変換・検証・保存の詳細を責務別モジュールへ委譲します。

```text
ソース設定（*.toml）
  ↓ sources.py：対象期間・URL・公表日・保存名の検証
公式Excel
  ↓ fetcher.py：取得・XLSX形式検証・manifest・SHA-256記録
Rawデータ
  ↓ parser.py：Excel固有形式から月次レコードへ正規化
共通レコード（models.py）
  ↓ validation.py：キー・件数・値範囲・内訳整合性の検証
検証済みレコード
  ↓ database.py：出典・マスター・月次ファクトをSQLiteへロード
hotel_market.sqlite3
  ↓ report.py：一覧とMarket Sheetを生成
静的HTMLレポート
```

`pipeline.py`はETLのオーケストレーションまでを担い、レポート生成はCLIがETL成功後に呼び出します。`fetch`、`build-db`、`report`相当のコマンドも分離しているため、取得済みExcelや既存DBから部分的に再実行できます。

#### ドメインごとの差分

| 処理 | 都道府県 | 市区町村 |
|---|---|---|
| 設定 | `sources.toml`／対象年 | `municipality_sources.toml`／対象年月・source ID・提供元 |
| 入力 | 年確定値Excelの第1・4・8表 | 月次第2次速報Excelの参考第5・6・8・11・12表 |
| 正規化の単位 | 都道府県×年月 | 市区町村×年月×客室規模区分 |
| 主な品質検証 | 47都道府県、12か月、全国値、重複・値範囲 | 掲載自治体、4客室区分、非表章、需要・施設数内訳 |
| DB更新 | 一時DBを全件生成し、既存市区町村テーブルを引き継いで原子的に置換 | 対象年月・公表区分の行を1トランザクションで置換 |
| レポート | 全国一覧＋47都道府県Market Sheet | 市区町村一覧＋掲載自治体Market Sheet |

```text
src/hotel_supply_demand/
├── cli.py                       共通CLIエントリーポイント
├── sources.py                   都道府県・年確定値ソース（移行予定）
├── fetcher.py                   現行の都道府県Excel取得
├── parser.py                    現行の都道府県parser
├── validation.py               現行の都道府県品質検証
├── database.py                 現行の都道府県DBロード
├── analysis.py                 都道府県分析
├── config.py                   分析・レポート設定
├── models.py                   都道府県月次共通レコード
├── pipeline.py                 都道府県処理のオーケストレーション
├── report.py                   全国・都道府県レポート
└── municipality/
    ├── models.py               市区町村月次共通レコード
    ├── fetcher.py              e-Stat原Excel取得・manifest管理
    ├── parser.py               市区町村参考表の検証・結合
    ├── validation.py           市区町村月次レコードの品質検証
    ├── database.py             市区町村ファクトの冪等ロード
    ├── pipeline.py             月次処理のオーケストレーション
    ├── report.py               市区町村一覧・Market Sheet生成
    └── sources.py              月次ソース設定の読込・検証
```

現在は都道府県モジュールがパッケージ直下、市区町村モジュールが`municipality/`配下にあります。これは現行実装を正確に示すものであり、`prefecture/`や`common/`はまだ存在しません。共通化は、コードレビューで重複と差分を確認した後に独立した構造変更として判断します。

### SQLiteデータモデル

都道府県推計値と市区町村実数は、集計基準が異なるため別ファクトとして同じSQLiteに保存します。各ファクトから、URL、公表日、取得日時、SHA-256を持つ出典テーブルへ追跡できます。

現行スキーマは8テーブルと4つの分析用Viewからなるため、ER図、複合キー、更新方式、Viewの定義を[SQLiteデータモデル](docs/data-model.md)へ分離しました。列の単位と欠測値の扱いは[データ辞書](docs/data-dictionary.md)を参照してください。

## ローカル実行

### 都道府県パイプライン

Python 3.11以上で仮想環境を作成し、`pyproject.toml`からインストールします。Excelパイプラインにe-StatのアプリケーションIDは不要です。

```bash
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/hotel-etl pipeline
```

この1コマンドで公式Excel 7ファイルを取得し、`data/raw/manifest.json`へ来歴を記録して、`data/processed/hotel_market.sqlite3`と`reports/latest/`の分析レポートを生成します。同じURL・ハッシュの取得済みファイルはスキップします。ネットワークを使わず取得済みExcelからDBだけを作り直す場合は次を実行します。

```bash
.venv/bin/hotel-etl build-db
```

既存DBからレポートだけを再生成する場合：

```bash
.venv/bin/hotel-etl monitor --target-year 2025 --base-year 2019
```

主な成果物は次のとおりです。

- [`reports/latest/index.html`](reports/latest/index.html)：全国客室稼働率の時系列と、需給・インバウンド・季節変動を統合した都道府県一覧
- `reports/latest/market-sheets/`：都道府県別KPI、客室稼働率、延べ宿泊者数・需要構造、調査対象施設数の推移を示すMarket Sheet
- `reports/latest/prefecture-market.csv`：47都道府県の分析結果
- `reports/latest/report-metadata.json`：データ公表日、件数、分析設定

都道府県別の平均稼働率は月次12値の単純平均です。指標定義と利用上の制約は[分析方法論](docs/methodology.md)、分析期間は[`analysis.toml`](analysis.toml)に明示しています。

特定年だけを検証する場合は、たとえば `--years 2019 2024 2025` を付けます。全テストは次で実行できます。

```bash
.venv/bin/python -m unittest discover -s tests -v
```

### 市区町村パイプラインの実行方法

設定済みのe-Stat第2次速報Excelを取得し、検証後に同じSQLiteへ市区町村月次ファクトをロードします。e-Stat APIのアプリケーションIDは不要です。

```bash
.venv/bin/hotel-etl municipality-pipeline
```

このコマンドは次を実行します。

1. `municipality_sources.toml`から提供元・調査年月・公表日・source IDを読み込む
2. `fileKind=0`の原Excelを`data/raw/municipality/`へ取得する
3. `manifest.json`へ取得日時・SHA-256・ファイルサイズを記録する
4. 参考第5・6・8・11・12表を市区町村・客室区分単位で結合する
5. キー、4客室区分、欠測、値範囲、需要・施設数内訳を検証する
6. `municipality_source_files`、`municipalities`、`monthly_municipality_market`へロードする
7. `reports/latest/municipalities/`へ市区町村一覧とMarket Sheetを生成する

生成物は次のとおりです。

- `reports/latest/municipalities/index.html`：都道府県絞り込み・市区町村検索が可能な一覧
- `reports/latest/municipalities/market-sheets/`：需要、外国人比率、稼働率、客室規模別内訳を示す個別ページ

DBを更新せずレポートだけ再生成する場合は次を使用します。

```bash
.venv/bin/hotel-etl municipality-report
```

取得だけ、または取得済みExcelからのDB再生成だけを行う場合は次を使用します。

```bash
.venv/bin/hotel-etl municipality-fetch --periods 2026-05
.venv/bin/hotel-etl municipality-build-db --periods 2026-05
```

同じ月を再実行した場合、URL・source ID・SHA-256が一致するExcelの再取得を省略し、SQLiteの対象月を1トランザクションで置き換えます。

特定月だけを更新する場合は、例えば`--periods 2026-05`を指定します。

### e-Stat API探索の実行方法

画像やチャットへ公開していない新しいe-StatアプリケーションIDを環境変数へ設定します。

```bash
read -s ESTAT_APP_ID
export ESTAT_APP_ID
echo
```

Codexなど別の実行セッションから利用する場合は、Git除外済みの`.env`へ保存できます。

```bash
read -s ESTAT_APP_ID
printf 'ESTAT_APP_ID=%s\n' "$ESTAT_APP_ID" > .env
unset ESTAT_APP_ID
echo
```

開発版をインストールせずに統計表を検索する場合：

```bash
PYTHONPATH=src python -m hotel_supply_demand.cli search-tables \
  --query '宿泊旅行統計調査' \
  --limit 20
```

統計表IDを特定した後は、メタ情報と少量のサンプルを取得できます。

```bash
PYTHONPATH=src python -m hotel_supply_demand.cli show-metadata \
  --stats-data-id '<統計表ID>'

PYTHONPATH=src python -m hotel_supply_demand.cli fetch-sample \
  --stats-data-id '<統計表ID>' \
  --limit 10
```

認証情報を必要としない初期テスト：

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## リポジトリと生成物の管理方針

依存関係は`pyproject.toml`に一本化しています。Google Colab・Notebook中心の旧実装と旧CSVは現行ツリーから除外し、Gitタグ`legacy-colab-final`から参照・復元できる状態にしています。Raw Excel、SQLite、`.env`はGit管理しません。

`reports/latest/`は、クラウド公開前にもポートフォリオの出力例をリポジトリ上でレビューできるよう、現段階では意図的にGit管理しています。静的サイトの自動デプロイ完成後に、デプロイ工程だけで生成する方針への切り替えを再検討します。

現在の主な課題は、旧実装由来の再現性不足ではなく、市区町村parser・品質ルール・分析指標・レポート表示のレビューと、安全な定期更新・クラウド公開です。実施順序と完了条件は[v2ロードマップ](plan_memo/v2-roadmap.md)に記載しています。
