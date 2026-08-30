.PHONY: help setup run redo concat upload run-upload test clean clean-output clean-work open assets

help:  ## このヘルプを表示
	@awk 'BEGIN{FS=":.*##"; printf "\n使い方: make \033[36m<target>\033[0m\n\n"} /^[a-zA-Z_-]+:.*##/ {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup:  ## 依存インストール (初回)
	uv sync

run:  ## パイプライン全部実行 (assets/ → output/jom.mp4)
	uv run jom

redo:  ## work/を再利用して連結だけやり直し
	uv run jom --skip-normalize

test:  ## テスト実行
	uv run pytest

concat:  ## redoのエイリアス
	uv run jom --skip-normalize

upload:  ## 生成済み動画をYouTubeにアップロード (output/jom.mp4)
	uv run jom-upload

run-upload:  ## パイプライン実行してそのままYouTubeへアップロード
	uv run jom --upload

open:  ## 最終動画を再生
	open output/jom.mp4

assets:  ## assetsフォルダをFinderで開く (動画追加用)
	open assets/

clean-work:  ## 正規化中間ファイル削除
	rm -rf work/

clean-output:  ## 最終出力削除
	rm -rf output/

clean: clean-work clean-output  ## 中間・出力すべて削除
