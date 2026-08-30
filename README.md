# jom

動画群を重複除去し、撮影日降順で連結、各動画の下部に撮影日をテロップとして焼き込むツール。

## 何をするか

1. `assets/` 内の動画を全部読む
2. 重複を検出して除外 (SHA-256 → pHash 二段構え)
3. 撮影日時 (メタデータの `date` → `creation_time` → ファイル更新日) の降順に並べる
4. 1920x1080 / 30fps / H.264 / AAC に正規化 (縦動画は左右黒帯レターボックス)
5. 画面下中央に半透明黒背景の白文字で日時テロップ (`YYYY-MM-DD HH:MM`) を焼き込む
6. `output/jom.mp4` に連結出力
7. (任意) そのまま YouTube にアップロード (`--upload`)

## 必要なもの

- macOS + [Homebrew](https://brew.sh/)
- `ffmpeg` (**libzimg / libplacebo 入り推奨**。iPhone の HDR (HLG/PQ) 動画を混ぜる場合は必須)
- `uv` (Python パッケージ管理)
- (YouTube アップロードを使う場合のみ) Google アカウントと OAuth クライアント → [YouTube アップロード](#youtube-アップロード) 参照

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

# 4. (任意) YouTube にアップロード
make upload
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
| `make upload` | 生成済み `output/jom.mp4` を YouTube にアップロード |
| `make run-upload` | 全工程実行してそのまま YouTube にアップロード |
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
uv run jom --upload              # 連結後そのままYouTubeへ

uv run jom-upload                       # output/jom.mp4 をアップロード
uv run jom-upload path/to/movie.mp4     # 任意の動画をアップロード
uv run jom-upload --privacy unlisted --title '家族旅行' --tags '旅行,2025'
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
│   ├── youtube.py      # YouTube Data API v3 アップロード
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

## YouTube アップロード

完成した動画を YouTube Data API v3 で直接アップロードできる。

### 初回セットアップ (OAuth クライアントの用意)

YouTube API は個人のチャンネルに書き込むため、自分用の OAuth クライアントが要る。

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作る (既存でも可)
2. 「APIとサービス」→「ライブラリ」で **YouTube Data API v3** を有効化
3. 「APIとサービス」→「OAuth同意画面」を設定 (ユーザーの種類: 外部 / 公開ステータス: テスト)。
   「テストユーザー」に自分の Google アカウントを追加する
4. 「APIとサービス」→「認証情報」→「認証情報を作成」→「OAuth クライアント ID」→
   アプリケーションの種類 **デスクトップアプリ** で作成し、JSON をダウンロード
5. その JSON を `~/.config/jom/client_secret.json` に置く

```bash
mkdir -p ~/.config/jom
mv ~/Downloads/client_secret_*.json ~/.config/jom/client_secret.json
```

### 認証の流れ

初回実行時にブラウザが開いて Google アカウントの許可を求められる。許可すると
`~/.config/jom/youtube_token.json` にトークン (パーミッション 600) が保存され、
2回目以降は自動で再利用・自動更新される。

SSH 越しなどブラウザを開けない環境では `--no-browser` を付けると URL が表示される。

要求するスコープは `https://www.googleapis.com/auth/youtube.upload` (アップロード専用)
のみで、既存動画の読み取りや削除はできない。

### 使い方

```bash
make upload                              # output/jom.mp4 を非公開でアップロード
make run-upload                          # 連結からアップロードまで一気に

uv run jom --upload --privacy unlisted   # パイプライン実行→限定公開でアップロード
uv run jom-upload path/to/movie.mp4 --title '家族旅行 2025' --tags '旅行,家族'
uv run jom-upload --description-file notes.txt
```

### アップロード用オプション

`jom --upload` と `jom-upload` で共通。

| オプション | 既定値 | 説明 |
|---|---|---|
| `--title` | 出力ファイル名 + 撮影日レンジ | 動画タイトル |
| `--description` | (空) | 説明文 |
| `--description-file` | - | 説明文をファイルから読む (`--description` より優先) |
| `--tags` | (空) | タグ。カンマ区切り (`旅行,家族`) |
| `--privacy` | `private` | `private` / `unlisted` / `public` |
| `--category-id` | `22` | YouTube のカテゴリID (22 = People & Blogs) |
| `--made-for-kids` | off | 子ども向けコンテンツとして申告 |
| `--client-secrets` | `~/.config/jom/client_secret.json` | OAuth クライアントシークレット JSON |
| `--token` | `~/.config/jom/youtube_token.json` | トークンの保存先 |
| `--no-browser` | off | ブラウザを自動起動せず URL 表示のみ |

`--client-secrets` / `--token` は環境変数 `JOM_YOUTUBE_CLIENT_SECRETS` /
`JOM_YOUTUBE_TOKEN` でも指定できる。

`--title` 未指定時は出力ファイル名 (拡張子なし) に撮影日レンジが付く
(例: `jom 2025-03-14〜2025-03-20`)。`jom-upload` で単体の動画を渡した場合は
撮影日が分からないためファイル名のみ。

### 仕様と注意

- 8MB チャンクの resumable upload。通信断や 5xx は指数バックオフで最大5回リトライ
- 既定は `private` (非公開)。意図せず公開されるのを防ぐため明示指定しない限り公開しない
- 未審査 (テストモード) の OAuth アプリからのアップロードは、`public` を指定しても
  YouTube 側で非公開に固定される。公開したい場合は YouTube Studio 側で変更する
- API クォータは既定 1日 10,000 ユニット、アップロード1本 1,600 ユニット (実質 1日6本程度)
- `client_secret*.json` と `*token*.json` は `.gitignore` 済み。**リポジトリにコミットしない**

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

- YouTube アップロードは 1日あたりのAPIクォータ (既定 10,000ユニット / 1本 1,600ユニット) の範囲でのみ可能 → 実質 1日6本程度
- 未審査 (テスト) の OAuth アプリでアップロードした動画は、`--privacy public` を指定しても YouTube 側で非公開に固定される (自分のチャンネルで公開設定に変更すればよい)
- pHash 閾値は経験値。誤検出/見逃しがあれば `src/jom/dedup.py` の `PHASH_THRESHOLD` を調整
- 音声指紋 (chromaprint) までは実装していない。極端な解像度変更や強クロップされた重複動画は検出できない可能性

## ライセンス

MIT License。詳細は [LICENSE](LICENSE) を参照。
