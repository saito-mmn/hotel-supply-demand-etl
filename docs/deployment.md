# GitHub Pages手動デプロイ

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

> [!NOTE]
> 2026年8月17日時点ではworkflowと公開前検証のローカル実装まで完了しており、GitHub上のPages初回設定、workflow実行、公開URLの実機確認は未実施です。

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

Phase 4は意図した生成結果を人が確認してから公開する手動デプロイです。公式ソースの更新検知、Excel取得、SQLite更新、HTML再生成、テスト、定期デプロイの自動化はPhase 6で扱います。
