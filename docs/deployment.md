# GitHub Pages・自動更新運用

## 公開構成

本プロジェクトのLive DemoはGitHub Pagesで配信します。公開するのは生成済み静的レポートだけで、SQLite、Raw Excel、manifest、認証情報をWebへ配置しません。

```text
reports/latest/（レビュー用生成物）
  ↓ scripts/prepare_pages.py：選別・件数検証・リンク検証・機密情報検査
.pages/（一時的な公開成果物、Git管理外）
  ↓ GitHub Actions
GitHub Pages
```

公開URL：<https://saito-mmn.github.io/hotel-supply-demand-etl/>

## workflowの分離

| workflow | 契機 | 外部公式サイト | 役割 |
|---|---|---|---|
| `ci.yml` | Pull Request、`main`へのpush | アクセスしない | install、lint、更新系の型検査、fixture test、リポジトリ・HTML検証 |
| `pages.yml` | 手動 | アクセスしない | Git管理中のレビュー済みHTMLを再公開 |
| `update-and-deploy.yml` | 定期、手動 | アクセスする | 更新検出、Excel取得、DB・HTML再生成、成功時のみ公開 |

通常のコード変更は固定fixtureだけで検証し、公式サイトの一時障害から切り離します。公式更新workflowが失敗した場合はdeploy jobへ進まないため、前回成功時のPagesが維持されます。

型検査はPhase 5・6で追加した更新検出・自動化モジュールから導入しています。既存parser・analysis・report・CLIを含む全`src`へのmypy拡張は、統合コードレビュー後の段階的な品質改善事項です。

## 初回設定

1. Phase 4の変更をデフォルトブランチへ反映する。
2. GitHubリポジトリの `Settings > Pages > Build and deployment > Source` で `GitHub Actions` を選択する。
3. 必要に応じて `Settings > Environments > github-pages` で、デフォルトブランチだけを許可するdeployment protection ruleを設定する。

## 手動デプロイ

1. GitHubの `Actions` を開く。
2. `Deploy static demo to GitHub Pages` を選ぶ。
3. `Run workflow` からデフォルトブランチを指定して実行する。
4. `build` と `deploy` が成功したこと、およびworkflow summaryに表示されるURLを確認する。

workflowはレポートを再生成しません。Gitでレビュー済みの`reports/latest/`を公開するため、デプロイ前に必要なパイプラインまたはreportコマンドを実行し、生成差分を確認します。

## 公式データの定期・手動更新

定期実行は、市区町村第2次速報を毎週火曜日、都道府県年確定値を6～8月の1日・15日に確認します。公表日は固定されないため、特定日1回ではなく確認期間を設けています。時刻はUTCです。

手動実行では`domain`に`all`、`municipality`、`prefecture`を指定できます。通常はデータ変更があった場合だけdeployします。データ変更なしでも現在の生成物を再公開する必要がある場合だけ、`deploy_without_update`を有効にします。

Actionsの実行環境は毎回破棄されるため、前回成功時のRaw Excel、manifest、SQLite、採用済みソース設定、生成レポートをActions Cacheへ保存します。キャッシュは高速化・差分検知の運用状態であり、公開artifactには含めません。更新結果、設定、manifestは30日間の監査artifactとして保存します。

`approval_required`など人の確認が必要な結果が1件でもある場合は、公式情報を確認するまで公開を停止します。新規データがなければ正常終了し、不要な再デプロイを行いません。

## ローカル事前検証

```bash
python3 scripts/prepare_pages.py
python3 -m http.server 8000 --directory .pages
```

ブラウザで <http://127.0.0.1:8000/> を開き、全国レポート、市区町村一覧、各Market Sheetへの遷移を確認します。`.pages/`は検証のたびに作り直され、Git管理されません。

## 公開前の検証内容

- 都道府県Market Sheet数が`report-metadata.json`の件数と一致する
- 市区町村Market Sheet数が市区町村側メタデータの件数と一致する
- HTML内の相対リンク先が公開成果物内に存在し、公開ルート外へ出ない
- シンボリックリンクを含まない
- 公開許可したHTML、CSS、JavaScript、画像・フォント以外を含まない
- `/Users/`、`/home/`、`ESTAT_APP_ID`、URL中の`appId`を含まない

検証に失敗した場合、artifactのアップロードとデプロイは実行されません。

## Phase 6との境界

Phase 4の手動デプロイは、Git管理中の生成物を公式サイトへアクセスせず再公開する復旧手段として残します。Phase 6の公式更新workflowは、公式ソースの更新検知、Excel取得、SQLite更新、HTML再生成、品質ゲート、成功時のデプロイを担います。
