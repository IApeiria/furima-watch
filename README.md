# furima-watch — フリマ・中古ショップ横断ウォッチャー

**日本語** | [English](README.en.md) | [简体中文](README.zh-CN.md)

欲しい中古品が「この値段以下」で出たら、すぐ Windows に通知します。
メルカリ・ヤフオク・PayPayフリマ・ラクマ・じゃんぱら・ソフマップ・ハードオフの 7 サイトを 1 回で巡回します。

もともとは RTX 4070 Ti SUPER を安く買うために作ったもので、設定ファイルを書き換えれば何でも監視できます。

## できること

- 7 サイトを横断して、価格条件に合う新着出品を探す
- タイトルの正規表現で「本体だけ」に絞る（空箱・ケーブル・PC 丸ごと・買取広告などを除外）
- ヤフオクは即決価格に加えて、**終了間近で現在価格が安いもの**も通知
- 一度通知した出品は覚えていて再通知しない（値下げで条件を満たし直したら再通知）
- 通知をクリックすると出品ページが開く。[ntfy.sh](https://ntfy.sh) を使えばスマホにも届く
- サイトの構成が変わって取得に失敗し続けたら、一度だけ知らせる

## 使い方

Python 3.11 以上が必要です（Windows 向け。通知に winotify を使っています）。

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.toml config.toml   # 監視したい商品と価格を書く
.venv\Scripts\python furima_watch.py --dry-run      # 通知せず、該当候補を表示するだけ
.venv\Scripts\python furima_watch.py --test-notify  # 通知の見た目を確認
.venv\Scripts\python furima_watch.py                # 1 回巡回して、新着があれば通知
```

### 定期実行（タスクスケジューラ）

1 回巡回して終わるスクリプトなので、タスクスケジューラで 15〜30 分おきに実行します。
`pythonw.exe` を使うとコンソール窓が出ません。

```bash
schtasks /create /tn furima-watch /sc minute /mo 20 /tr "\"C:\path\to\furima-watch\.venv\Scripts\pythonw.exe\" \"C:\path\to\furima-watch\furima_watch.py\""
```

## 設定（config.toml）

監視したい商品ごとに `[[watch]]` を書きます。詳しくは [config.example.toml](config.example.toml) を見てください。

| 項目 | 意味 |
|---|---|
| `name` | 通知に出る名前 |
| `queries` | フリマ・オークションで検索する語（複数可） |
| `shop_query` | じゃんぱら・ソフマップ・ハードオフで検索する語（省略時は `queries` の 1 つ目） |
| `min_price` / `max_price` | 価格の範囲（円）。安すぎるものは箱やケーブルのことが多いので下限も設定するのがおすすめ |
| `target` | タイトルがどれかに一致したら対象（正規表現のリスト。空なら検索結果すべて） |
| `exclude` | タイトルがどれかに一致したら除外 |
| `include_junk` | ジャンク品も通知するか |

## 注意

- 各サイトの非公式な取得方法を使っています。サイト側の変更で動かなくなることがあります。
- 利用は個人の範囲で、巡回間隔は長めにしてください（サイトに負担をかけないため）。各サイトの利用規約はご自身で確認してください。
- 購入判断は必ず出品ページを自分の目で確認してから。

## License

MIT
