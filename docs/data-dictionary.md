# Phase 1 データ辞書

Phase 1は観光庁「宿泊旅行統計調査」の年確定値Excelを、都道府県・年月・公表区分単位へ正規化する。入力は第1表、第4表、第8表の「全体」列であり、施設タイプ別内訳はMVP対象外とする。

## `source_files`

| 列 | 型 | 内容 |
|---|---|---|
| `year`, `release_type` | INTEGER, TEXT | 調査対象年と公表区分 |
| `url`, `filename` | TEXT | 公式Excelの取得元と保存名 |
| `published_on` | TEXT | 観光庁による当該年次確定値の公表日（ISO 8601日付） |
| `retrieved_at` | TEXT | ファイルを取得した日時（ISO 8601日時） |
| `sha256`, `size_bytes` | TEXT, INTEGER | ファイル同一性確認用のハッシュとサイズ |

レポートには対象年・対象公表区分の`published_on`を「データ公表日」として表示する。`retrieved_at`はデータ来歴には保持するが、統計の鮮度を示す日付としては使用しない。

## `monthly_demand`

| 列 | 型 | 内容 |
|---|---|---|
| `year`, `month` | INTEGER | 調査対象年月 |
| `prefecture_code` | INTEGER | 1～47の都道府県コード |
| `release_type` | TEXT | Phase 1では`final` |
| `total_guests` | INTEGER NULL | 延べ宿泊者数（人泊） |
| `japanese_guests` | INTEGER NULL | `total_guests - foreign_guests`。いずれか欠測ならNULL |
| `foreign_guests` | INTEGER NULL | 外国人延べ宿泊者数（人泊） |
| `occupancy_rate` | REAL NULL | 客室稼働率（%） |
| `source_file_id` | INTEGER | `source_files`への外部キー |

## `monthly_supply`

| 列 | 型 | 内容 |
|---|---|---|
| `year`, `month`, `prefecture_code`, `release_type` | - | 需要テーブルと同じ粒度 |
| `facilities` | INTEGER NULL | 調査対象施設数 |
| `source_file_id` | INTEGER | `source_files`への外部キー |

## `national_occupancy`

| 列 | 型 | 内容 |
|---|---|---|
| `year`, `month` | INTEGER | 調査対象年月 |
| `release_type` | TEXT | Phase 1では`final` |
| `occupancy_rate` | REAL | 観光庁Excel第8表に掲載された全国客室稼働率（%） |
| `source_file_id` | INTEGER | `source_files`への外部キー |

全国レポートでは都道府県値の単純平均を作らず、この公式全国値を使用する。

## 欠測値

Excelの空欄、`-`、`…`、`...`、`X`、`*`はゼロへ変換せずSQLiteの`NULL`とする。原表で観測されないことと、実績がゼロであることを区別するためである。

## 分析用View

| View | 内容 |
|---|---|
| `latest_monthly_demand` | 同一年月・都道府県について、確定値、第2次速報、第1次速報の順で需要データを選択 |
| `latest_monthly_supply` | 同じ優先順位で供給データを選択 |
| `monthly_market` | 最新需要・供給・都道府県名を結合した月次分析データ |
| `annual_market` | 12か月の需要合計、稼働率平均、施設数平均を集計した年次分析データ |

Phase 2の派生指標はファクトテーブルへ重複保存せず、Viewと`analysis.py`から再計算する。指標定義は[分析方法論](methodology.md)を参照する。
