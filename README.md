# jom

動画群を重複除去し、撮影日降順で連結、各動画の下部に撮影日をテロップとして焼き込むツール。

## 何をするか

1. `assets/` 内の動画を全部読む
2. 重複を検出して除外 (SHA-256 → pHash 二段構え)
3. 撮影日時 (メタデータの `date` → `creation_time` → ファイル更新日) の降順に並べる
4. 1920x1080 / 30fps / H.264 / AAC に正規化 (縦動画は左右黒帯レターボックス)
5. 画面下中央に半透明黒背景の白文字で日時テロップ (`YYYY-MM-DD HH:MM`) を焼き込む
6. `output/jom.mp4` に連結出力

## 必要なもの

- macOS + [Homebrew](https://brew.sh/)
- `ffmpeg` (**libzimg / libplacebo 入り推奨**。iPhone の HDR (HLG/PQ) 動画を混ぜる場合は必須)
- `uv` (Python パッケージ管理)

Homebrew 標準の `brew install ffmpeg` は libzimg/libplacebo 非対応のため、HDR 動画が混ざると色が崩れる。HDR を扱うなら以下を推奨:

```bash
brew tap homebrew-ffmpeg/ffmpeg
brew uninstall --ignore-dependencies ffmpeg      # 標準版がある場合
brew install homebrew-ffmpeg/ffmpeg/ffmpeg --with-zimg --with-libplacebo
brew install uv
```

SDR 動画しか扱わない場合は標準版でも動く (`zscale` 検出時のみ HDR トーンマップを実施)。

## セットアップ

```bash
make setup    # uv sync で依存インストール
```

## 使い方

```bash
# 1. Finder で assets/ を開いて動画を放り込む
make assets

# 2. パイプライン実行
make run

# 3. 出力を再生
make open
```

### コマンド一覧

```bash
make help
```

| ターゲット | 用途 |
|---|---|
| `make setup` | 初回の依存インストール |
| `make run` | 全工程実行 (`assets/` → `output/jom.mp4`) |
| `make redo` | `work/` の正規化済みを再利用して連結だけやり直し |
| `make open` | 最終動画を再生 |
| `make assets` | `assets/` フォルダを Finder で開く |
| `make test` | テスト実行 |
| `make clean-work` | 正規化中間ファイル削除 |
| `make clean-output` | 最終出力削除 |
| `make clean` | 上記両方 |

### CLI 直接

```bash
uv run jom                       # デフォルト
uv run jom --name mymix.mp4      # 出力名指定
uv run jom --skip-normalize      # work/再利用
uv run jom --assets /path/to/dir # 別ディレクトリを対象
```

## ディレクトリ構成

```
jom/
├── assets/         # ユーザーが動画を放り込む (git ignore)
├── work/           # 正規化中間ファイル (git ignore)
├── output/         # 最終出力 (git ignore)
├── src/jom/
│   ├── metadata.py     # ffprobe → 撮影日/解像度抽出
│   ├── dedup.py        # SHA-256 + pHash 重複検出
│   ├── normalize.py    # 1080p化 + 日付PNG overlay
│   ├── concat.py       # concat demuxer で連結
│   └── main.py         # CLI エントリ
├── tests/
├── Makefile
└── pyproject.toml
```

## 重複検出の仕組み

同じ動画が別ファイル名/別アプリ経由で重複した場合を想定した二段検出。

### Stage 1: SHA-256

ファイルサイズでバケット化 → 同サイズ内のみ SHA-256 計算。バイト完全一致を除外。

### Stage 2: pHash (再エンコード耐性)

`duration` 差 ±0.6 秒以内の動画同士のみ、5フレーム (10/30/50/70/90%地点) を抽出して pHash 合成 → ハミング距離 ≤ 12 で重複判定。LINE や Instagram で再圧縮された動画も検出できる。

### 代表選択

重複と判定されたグループからは、**解像度が最も高い** → 同じなら**ファイルサイズが最大**のものを残す。

## 撮影日時について

優先順位:

1. `assets/dates.txt` による手動オーバーライド (下記参照)
2. `ffprobe` で取得できる `format.tags.date` (タイムゾーン付き。iPhone等が撮影時ローカル時刻で書き込む)
3. `format.tags.creation_time` (通常UTC。`date` が無い動画向け)
4. ファイルの mtime (共有経由でメタデータが剥がれた動画向けフォールバック)

TZ 付きのタグは端末のローカルタイムゾーンに変換して表示する。

### 手動オーバーライド (`assets/dates.txt`)

メタデータが無い/間違っている動画に対して、テキストファイルで日時を指定できる。書式:

```text
# コメント行 (先頭が # の行は無視、空行も無視)
IMG_2566.MOV,2020-01-15T10:00:00+09:00
old_video.mp4,2019-06-30T18:30:00+09:00
# 基準日 (指定すると全動画の日時テロップに (day N) が付く)
epoch,2020-01-15T00:00:00+09:00
```

- 各行は `<ファイル名>,<ISO 8601 日時>` の形式
- ファイル名は `assets/` 内のベース名 (パス無し、大文字小文字区別)
- 日時は ISO 8601。タイムゾーン付き推奨 (`+09:00` 等)。省略時はローカル時刻扱い
- `dates.txt` は git 管理対象外 (`assets/.gitignore` で除外済み)
- 対応する動画が無いエントリは警告表示のみで無視 (エラーにはしない)

`epoch` は予約語で、指定した日を「day 1」として、全動画の日時テロップの末尾に `(day N)` を付与する (N = 撮影日 − epoch日 + 1、日付部分のみで計算)。イベント/旅行の N日目表示に使う。同名の動画ファイルには `epoch` は使えない。

動画自体の `date` タグを書き換えたい場合は README 末尾 「動画のタグを直接書き換える」参照。

## 正規化仕様

| 項目 | 値 |
|---|---|
| 解像度 | 1920x1080 (レターボックス、はみ出さない) |
| フレームレート | 30fps |
| 映像コーデック | H.264 (libx264, CRF 20, preset medium) |
| ピクセルフォーマット | yuv420p |
| 音声コーデック | AAC 192kbps / 48kHz / stereo |
| 音声なし入力 | anullsrc で無音を挿入 |
| MP4 flags | `+faststart` |
| 色空間 | BT.709 / tv-range に明示タグ付け (連結時のプレイヤー解釈揺れ防止) |
| HDR 入力 | HLG/PQ を検出したら `zscale + tonemap=hable` で SDR (BT.709) 化。`zscale` が無い場合は WARN 表示のみで変換せず、発色が崩れる |
| BT.2020 SDR 入力 | `colorspace` フィルタで BT.709 に変換 |

## テロップ仕様

- 内容: `YYYY-MM-DD HH:MM` (秒は省略)。`dates.txt` に `epoch` 指定があれば末尾に ` (day N)` を追加
- 位置: 画面下中央 (下端から 30px)
- フォントサイズ: 40px
- 色: 白 (`#FFFFFF`)
- 背景: 半透明黒 (`#000000` α=128)、パディング横 20px 縦 10px
- フォント: システムの Helvetica / HelveticaNeue / Arial のいずれか

Pillow で PNG を生成 → ffmpeg の `overlay` フィルタで合成している (レイアウトを Python 側で完結させるため。標準版 Homebrew ffmpeg には `drawtext` が無い都合もある)。

## 動画のタグを直接書き換える

`dates.txt` を使わず動画ファイルの `date` タグ自体を修正したい場合は ffmpeg で再エンコードなしに可能。

```bash
# 単一ファイル
ffmpeg -i input.mov -c copy -metadata date="2025-03-14T10:30:00+09:00" output.mov

# 元ファイル置換
ffmpeg -y -i input.mov -c copy -metadata date="2025-03-14T10:30:00+09:00" tmp.mov \
  && mv tmp.mov input.mov

# 一括
for f in assets/*.mov; do
  ffmpeg -y -i "$f" -c copy -metadata date="2025-03-14T10:30:00+09:00" "$f.tmp.mov" \
    && mv "$f.tmp.mov" "$f"
done
```

確認:
```bash
ffprobe -v error -show_entries format_tags=date,creation_time -of default=nw=1 input.mov
```

## 制限事項

- YouTube アップロードは未実装 (今後追加予定)
- pHash 閾値は経験値。誤検出/見逃しがあれば `src/jom/dedup.py` の `PHASH_THRESHOLD` を調整
- 音声指紋 (chromaprint) までは実装していない。極端な解像度変更や強クロップされた重複動画は検出できない可能性

## ライセンス

MIT License。詳細は [LICENSE](LICENSE) を参照。
