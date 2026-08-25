## Processed Data（加工済みデータ）

このフォルダには、Notebook実行により生成された分析用の加工済みデータを格納しています。

### ファイル一覧

- `hotel_master_with_facility_with_index.csv`  
  - 都道府県別・年月別の宿泊統計に対し、需給指標・回復指数・変動リスク等を付与したデータ

- `hotel_master_yearly_with_index.csv`  
  - 上記データを年次（2019年基準）で集計した分析用データ

### 補足

- これらのCSVは、BIツールや別Notebookでの再分析を想定した中間成果物です
- 元データは `data/raw/` を参照してください
