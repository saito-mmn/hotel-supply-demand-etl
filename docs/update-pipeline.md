# 公式データ更新パイプライン

## 目的

e-Statの年確定値と月次第2次速報について、公式一覧ページの確認からExcel取得、品質検証、SQLite反映、静的HTML再生成までを同じCLIで実行します。更新途中の失敗で、現在利用できるDBとレポートを壊さないことを優先します。

## 更新確認

```bash
.venv/bin/hotel-etl check-updates
```

このコマンドは公式一覧ページのHTMLだけを取得し、Excel、SQLite、レポートを変更しません。

- 市区町村：e-Statの「宿泊旅行統計調査（第2次速報値）」から、調査年月、公表（更新）日、`statInfId`、`fileKind=0`の原Excelリンクを検出する
- 都道府県：e-Statの「宿泊旅行統計調査（年確定値）」から、調査年、公表（更新）日、`statInfId`、`fileKind=0`の原Excelリンクを検出する
- 第1次速報、閲覧用Excel（`fileKind=4`）、報道発表資料、広域市町村参考表を採用しない

## 更新実行

```bash
.venv/bin/hotel-etl update
```

```text
公式一覧ページから候補検出
  ↓
条件付きHTTPリクエスト／SHA-256比較
  ↓ 変更あり
一時DBへparse・品質検証・ロード
  ↓
一時ディレクトリへ全Market Sheet生成
  ↓ 全工程成功
DB・HTML・ソース設定をまとめて切替
```

変更がない場合は`updated: false`で正常終了し、DBとHTMLを変更しません。`ETag`または`Last-Modified`が提供される場合は条件付きリクエストを利用し、提供されない場合は再取得したファイルのSHA-256を比較します。

## ドメイン別実行と手動再処理

```bash
.venv/bin/hotel-etl update --domain municipality
.venv/bin/hotel-etl update --domain prefecture
.venv/bin/hotel-etl update --domain municipality --periods 2026-05
.venv/bin/hotel-etl update --domain prefecture --years 2025
```

`--periods`と`--years`は、同じハッシュでも指定期間を再度parse・検証・DB反映する手動再処理です。

## 来歴と訂正

`published_on`は、現在採用するファイルについて公式一覧または設定に記録された公表（更新）日です。URL、source IDまたはSHA-256が変わった場合、manifestの現在値を置き換える前に、旧URL、旧source ID、旧公表日、旧取得日時、旧SHA-256、旧サイズを`revisions`へ保存します。

同一URLの内容差し替えも、リモートファイルのSHA-256が変われば更新として扱います。

## 自動採用しないケース

- e-Statに原Excelリンクがなく、観光庁ファイルを例外採用する場合
- 設定済みの観光庁例外と、後から検出したe-Stat source IDが競合する場合
- 同じ対象期間に異なる複数の原Excelリンクが検出された場合

市区町村の観光庁例外は、`config/municipality_sources.toml`へ明示したものだけを継続利用します。年確定値はe-Statに調査年、公表（更新）日、原Excelが揃うため、新規年と訂正版を自動検出します。日付やURLを推測せず、同じ年に複数の原Excelがある場合は停止します。

e-Stat年確定値原Excelには、都道府県コードや各表の対象年月キャプションを省略した版があります。parserは都道府県名とシート名から同じ共通スキーマへ変換し、キャプションが存在する場合は従来どおり対象年月を検証します。

## 失敗時の扱い

parser、品質検証、SQLiteロード、HTML生成のいずれかが失敗した場合、一時成果物を採用せず、既存DB・既存HTML・ソース設定を維持します。複数成果物の切替途中でOSエラーが発生した場合も、退避した旧成果物を復元します。

Raw Excelとmanifestは再試行可能な取得キャッシュです。DB反映前に失敗した場合、新しいRawファイルが残ることがありますが、次回実行時にmanifest・ハッシュを再検証します。

## GitHub Actionsでの実行

`.github/workflows/update-and-deploy.yml`は、市区町村を週次、都道府県を年確定値の確認期間中に定期実行します。手動実行ではドメインを選択できます。コード品質、fixture test、更新処理、公開HTML検証を順に行い、すべて成功した場合だけGitHub Pagesへ反映します。

新規データなしは正常終了してdeployを省略します。設定または人の承認が必要な候補、parser・品質検証・HTML検証の失敗、公式サイト障害ではdeployせず、前回成功時の公開サイトを維持します。
