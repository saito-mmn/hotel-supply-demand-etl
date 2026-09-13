# Tableau用データセット

## 目的

静的HTMLは定型モニタリング、Tableau Publicは地域・期間を切り替える探索と比較を担当する。Tableauを加工基盤にはせず、SQLiteで確定した月次ファクトと比較指標をCSVへ出力する。

```text
公式Excel → ETL・Validation → SQLite
                              ├─ 静的HTML
                              └─ export-bi → CSV → Tableau Public
```

## 生成方法

```bash
.venv/bin/hotel-etl export-bi
```

既定の出力先は`exports/tableau/`である。出力先はGit管理せず、SQLiteから再生成する。

```text
exports/tableau/
├─ prefecture_monthly.csv
├─ municipality_monthly.csv
└─ metadata.csv
```

出力は一時ディレクトリで生成・検証してからディレクトリ単位で切り替える。DB不備、schema不一致、キー重複、値域・需要内訳の不整合がある場合は、既存の正常なCSVを保持する。

オプション：

```bash
.venv/bin/hotel-etl export-bi \
  --database data/processed/hotel_market.sqlite3 \
  --output-dir exports/tableau \
  --base-year 2019
```

## `prefecture_monthly.csv`

粒度は`date × geography_level × prefecture_code × release_type`である。47都道府県に加え、比較線として観光庁公表の全国客室稼働率を`geography_level=national`、`prefecture_code=00`で収録する。全国行は都道府県の単純平均ではなく、需要・施設数は含まない。

主な列：

| 列 | 内容 |
|---|---|
| `date`, `year`, `month` | 月初日、年、月 |
| `country_code`, `country_name` | Tableauの地理認識に使う`JP`・`日本` |
| `geography_level` | `national`または`prefecture` |
| `prefecture_code`, `prefecture_name` | 地域コード・名称 |
| `facility_type_code`, `facility_type_name` | MVPでは`all`・`全施設`。施設タイプ別ETLの拡張点 |
| `guest_nights_*` | 総・日本人・外国人延べ宿泊者数 |
| `foreign_share_pct` | 同一行の外国人数÷総数。期間集計時は分子・分母から再計算する |
| `occupancy_rate_pct` | 月次客室稼働率 |
| `occupancy_yoy_delta_pp` | 同一地域・同月の前年差（pt） |
| `occupancy_2019_delta_pp` | 同一地域・同月の2019年差（pt） |
| `has_*_comparison` | 比較対象が揃う場合は1。選択期間の比較可否判定に使用する |
| `facility_count` | 調査対象施設数 |
| `source_*` | URL、ファイル名、公表日、取得日時、SHA-256 |
| `dataset_generated_at` | CSV生成日時（UTC） |

## `municipality_monthly.csv`

Tableauで月次の欠損を線で接続しないよう、全307自治体について収録期間の全月を出力する。公式表に掲載されなかった月は`record_status=not_listed`とし、指標値をNULLのまま保持する。

粒度は`date × municipality_key`で、客室規模区分はダッシュボードの二重集計を避けるため`room_size_class=total`だけを収録する。

主な追加列：

| 列 | 内容 |
|---|---|
| `municipality_key` | `都道府県コード:市区町村名`の分析用キー |
| `record_status` | `published`または`not_listed` |
| `population_facility_count` | 母集団施設数 |
| `responding_facility_count` | 回収施設数 |
| `coverage_start_date`, `coverage_end_date`, `coverage_months` | 自治体の掲載期間・掲載月数 |
| `source_stat_inf_id` | e-Statの`statInfId`または明示した例外ID |

市区町村第2次速報は都道府県確定値と母集団・掲載基準が異なる。Tableau上で選択都道府県を引き継いで画面遷移しても、市区町村値を合計して都道府県値を作らない。

## `metadata.csv`

データセットごとの行数、公式掲載行数、対象期間、公表区分、集計範囲、出典、CSV生成日時を収録する。ダッシュボードのprovenance表示と更新確認に使用する。

## Tableau側の計算

期間の外国人比率は月次比率の平均ではなく、分子・分母から計算する。

```text
SUM([guest_nights_foreign]) / SUM([guest_nights_total]) * 100
```

前年差・2019年差を期間平均として表示する場合、選択した全月で比較対象が揃うことを`MIN([has_yoy_comparison])`または`MIN([has_2019_comparison])`で確認し、0を含む場合はKPIを非表示にする。

## 想定するDashboard

1. **都道府県市場**：KPI、公式全国値を含む稼働率時系列、日本人・外国人需要構成、日本地図、一覧
2. **市区町村市場**：都道府県・自治体filter、時系列、需要構成、施設数、掲載期間・欠損
3. **施設タイプ別**：第1・4・8表の追加ETL後に実装
4. **国籍別インバウンド**：施設タイプ別MVP後、20室以上施設の独立ファクトとして実装

Tableau PublicへのMVP公開は手動refreshとし、自動更新は完成条件に含めない。

## 自動更新（Google Sheets経由）

Tableau Publicが自動リフレッシュに対応するデータソースはGoogle Sheets／OneDrive／Dropbox／Boxに限られ、GCS等の汎用ストレージには対応しない。そのため、`update-and-deploy.yml`の`update`ジョブが公式データの更新を検知した回（`should_deploy=true`）に限り、以下を自動実行してGoogle Sheetsへ反映する。

```text
hotel-etl update（SQLite更新・レポート再生成）
  └─ should_deploy=true の場合のみ
       hotel-etl export-bi        （SQLite → exports/tableau/*.csv）
       hotel-etl sync-sheets      （CSV → Google Sheetsの各タブを全置換）
```

ローカルの`data/processed/*`はGit管理外で自動更新されないため、`export-bi`と`sync-sheets`は必ずCI内・`hotel-etl update`直後の同一SQLiteに対して実行する。反映頻度はTableau独自のスケジュール更新ではなく、`update-and-deploy.yml`のチェック頻度（市区町村：毎週火曜、都道府県確定値：6〜8月の1日・15日）に一致する。

### `hotel-etl sync-sheets`

```bash
.venv/bin/hotel-etl sync-sheets \
  --csv-dir exports/tableau \
  --spreadsheet-id <スプレッドシートID> \
  --credentials-file <サービスアカウントJSONキー>
```

`--credentials-file`を省略した場合は環境変数`GOOGLE_SHEETS_CREDENTIALS_JSON`（JSON文字列そのもの）を読む。対象スプレッドシートには`prefecture_monthly`・`municipality_monthly`・`metadata`という名前のタブを事前に用意し、書き込みを行うサービスアカウントをEditorとして共有しておく。実行のたびに各タブの内容を丸ごとクリアしてCSVで置き換える。

書き込みは`value_input_option=USER_ENTERED`（Sheetsに人間が入力したのと同様に型推測させる）で行うため、Tableau側で数値・日付列がテキストではなく数値・日付型として読み込まれる。ただし`prefecture_code`のようなゼロ埋めコードや`source_stat_inf_id`・`source_sha256`のような数字だけになり得るID列は誤って数値化されるとゼロ埋めが消えるため、`sheets_sync.FORCE_TEXT_COLUMNS`に列挙してテキストとして強制する（先頭に`'`を付与するSheetsの標準的な回避策）。

インストールには`sheets` extra（`gspread`・`google-auth`）が必要（`pip install -e ".[sheets]"`）。

### 初回セットアップ（手動・一度だけ）

1. Google Cloudでプロジェクトを作成し、Google Sheets APIを有効化する
2. サービスアカウントを作成し、JSONキーを発行する
3. 対象のGoogle Sheetsを作成し、`prefecture_monthly`・`municipality_monthly`・`metadata`の3タブを用意して、サービスアカウントのメールアドレスをEditorとして共有する
4. そのGoogle SheetsをTableau Publicのデータソースとして接続し、ワークブックの設定でスケジュール更新（自動リフレッシュ）を有効化する
5. GitHubリポジトリに以下を登録する
   - Secret `GOOGLE_SHEETS_CREDENTIALS_JSON`：手順2のJSONキーの中身
   - Variable `TABLEAU_SPREADSHEET_ID`：手順3のスプレッドシートID

この2つが未設定の間、`update-and-deploy.yml`の同期ステップは自動的にスキップされる（既存のレポート生成・Pages公開には影響しない）。
