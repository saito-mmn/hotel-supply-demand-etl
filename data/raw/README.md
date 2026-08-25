## データソース（Raw Data Sources）

本プロジェクトでは、以下の公的統計データを需要側の時系列データとして使用しています。

### 観光庁「宿泊旅行統計調査」（公式サイト）
- 最新の月次推移表を需要側データとして利用
- 都道府県別・月次の延べ宿泊者数、外国人宿泊者数等を取得
- リンク：[観光庁 宿泊旅行統計調査](https://www.mlit.go.jp/kankocho/tokei_hakusyo/shukuhakutokei.html)

### e-Stat（政府統計ポータルサイト）
- 宿泊旅行統計調査のデータセットを一括ダウンロード可能
- 年次・月次データを横断的に取得・補完する用途で利用
- リンク：[宿泊旅行統計調査 データセット一覧](https://www.e-stat.go.jp/stat-search/files?page=1&layout=dataset&toukei=00601020&kikan=00601&tstat=000001079598&cycle=7&result_back=1&tclass1val=0)
---

### 補足
- 元データは再配布制限および容量の観点から、本リポジトリには同梱していません
- 上記リンクより取得したCSVを `data/raw/` 配下に配置してください
- 取得後、Notebookを上から順に実行することで分析結果を再現できます

