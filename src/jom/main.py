"""jom CLI: assets/ を重複除去→日付降順で連結→output/ (→ YouTube)"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Sequence

import click

from .concat import concat
from .dedup import dedup
from .metadata import probe
from .normalize import normalize
from .overrides import load_overrides
from .youtube import (
    DEFAULT_CATEGORY_ID,
    DEFAULT_CLIENT_SECRETS,
    DEFAULT_PRIVACY,
    DEFAULT_TOKEN_FILE,
    PRIVACY_CHOICES,
    UploadError,
    UploadRequest,
    default_title,
    parse_tags,
    resolve_description,
    upload,
    watch_url,
)

VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}
OVERRIDES_FILE = "dates.txt"
DEFAULT_OUTPUT = Path("output") / "jom.mp4"


def _collect(assets_dir: Path) -> list[Path]:
    return sorted(
        p for p in assets_dir.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


def youtube_options(f):
    """`jom --upload` と `jom-upload` で共通のアップロードオプション"""
    opts = [
        click.option("--title", default=None,
                     help="動画タイトル (既定: 出力ファイル名 + 撮影日レンジ)"),
        click.option("--description", default="", help="動画の説明文"),
        click.option("--description-file",
                     type=click.Path(exists=True, dir_okay=False, path_type=Path),
                     default=None, help="説明文をファイルから読む (--description より優先)"),
        click.option("--tags", default="", help="タグ (カンマ区切り)"),
        click.option("--privacy", type=click.Choice(PRIVACY_CHOICES),
                     default=DEFAULT_PRIVACY, show_default=True, help="公開範囲"),
        click.option("--category-id", default=DEFAULT_CATEGORY_ID, show_default=True,
                     help="YouTube のカテゴリID (22 = People & Blogs)"),
        click.option("--made-for-kids", is_flag=True, help="子ども向けコンテンツとして申告"),
        click.option("--client-secrets", type=click.Path(path_type=Path),
                     envvar="JOM_YOUTUBE_CLIENT_SECRETS", default=DEFAULT_CLIENT_SECRETS,
                     show_default=True, help="OAuth クライアントシークレット JSON"),
        click.option("--token", "token_file", type=click.Path(path_type=Path),
                     envvar="JOM_YOUTUBE_TOKEN", default=DEFAULT_TOKEN_FILE,
                     show_default=True, help="OAuth トークンの保存先"),
        click.option("--no-browser", is_flag=True,
                     help="認証時にブラウザを自動起動せず URL を表示するだけにする"),
    ]
    for opt in reversed(opts):
        f = opt(f)
    return f


def _do_upload(video: Path, *, title: str | None, description: str,
               description_file: Path | None, tags: str, privacy: str, category_id: str,
               made_for_kids: bool, client_secrets: Path, token_file: Path,
               no_browser: bool, dates: Sequence[datetime] | None = None) -> str:
    """UploadRequest を組み立ててアップロード。視聴URLを返す"""
    try:
        req = UploadRequest(
            path=video,
            title=title or default_title(video, dates),
            description=resolve_description(description, description_file),
            tags=parse_tags(tags),
            privacy=privacy,
            category_id=category_id,
            made_for_kids=made_for_kids,
        )
        click.echo(f"  タイトル: {req.title}")
        click.echo(f"  公開範囲: {req.privacy}")

        shown = -1

        def progress(ratio: float) -> None:
            nonlocal shown
            pct = int(ratio * 100)
            if pct != shown:
                shown = pct
                click.echo(f"\r  送信中 {pct:3d}%", nl=False)

        video_id = upload(
            req,
            client_secrets=client_secrets,
            token_file=token_file,
            open_browser=not no_browser,
            progress=progress,
        )
    except (UploadError, ValueError) as e:
        click.echo("")
        raise click.ClickException(str(e)) from e
    click.echo("")
    url = watch_url(video_id)
    click.echo(f"  URL: {url}")
    return url


@click.command()
@click.option("--assets", "assets_dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=Path("assets"), show_default=True)
@click.option("--work", "work_dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path("work"), show_default=True)
@click.option("--output", "output_dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path("output"), show_default=True)
@click.option("--name", default="jom.mp4", show_default=True, help="出力ファイル名")
@click.option("--skip-normalize", is_flag=True, help="正規化済みファイル(work/)を再利用")
@click.option("--upload", "do_upload", is_flag=True, help="完成した動画を YouTube にアップロード")
@youtube_options
def cli(assets_dir: Path, work_dir: Path, output_dir: Path, name: str, skip_normalize: bool,
        do_upload: bool, **yt) -> None:
    """assetsの動画を重複除去→日付降順で連結"""
    files = _collect(assets_dir)
    if not files:
        raise click.ClickException(f"動画無し: {assets_dir}")

    total = 6 if do_upload else 5
    click.echo(f"[1/{total}] メタデータ抽出 ({len(files)}件)")
    metas = [probe(p) for p in files]

    overrides = load_overrides(assets_dir / OVERRIDES_FILE)
    if overrides.epoch is not None:
        click.echo(f"  epoch: {overrides.epoch.strftime('%Y-%m-%d')} (以降 (day N) を付与)")
        for m in metas:
            m.epoch = overrides.epoch
    if overrides.dates:
        applied = 0
        unmatched = set(overrides.dates) - {m.path.name for m in metas}
        for m in metas:
            if m.path.name in overrides.dates:
                m.creation_time = overrides.dates[m.path.name]
                applied += 1
                click.echo(f"  override: {m.path.name} -> {m.date_label}")
        click.echo(f"  {OVERRIDES_FILE} から {applied}件適用")
        for missing in sorted(unmatched):
            click.echo(f"  警告: {OVERRIDES_FILE} の '{missing}' に対応する動画無し")

    click.echo(f"[2/{total}] 重複検出")
    survivors, dropped = dedup(metas)
    for loser, keeper in dropped:
        click.echo(f"  除外: {loser.path.name} -> 代表 {keeper.path.name}")
    click.echo(f"  {len(metas)}件 -> {len(survivors)}件")

    click.echo(f"[3/{total}] 日付降順ソート")
    survivors.sort(key=lambda m: m.creation_time, reverse=True)
    for m in survivors:
        click.echo(f"  {m.date_label}  {m.path.name}  ({m.width}x{m.height}, {m.duration:.1f}s)")

    click.echo(f"[4/{total}] 正規化+日付焼き込み")
    work_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[Path] = []
    for i, m in enumerate(survivors, 1):
        out = work_dir / f"{i:03d}_{m.path.stem}.mp4"
        if skip_normalize and out.exists():
            click.echo(f"  ({i}/{len(survivors)}) skip {out.name}")
        else:
            click.echo(f"  ({i}/{len(survivors)}) {m.path.name} -> {out.name}")
            normalize(m, out)
        normalized.append(out)

    click.echo(f"[5/{total}] 連結")
    final = output_dir / name
    concat(normalized, final)
    click.echo(f"完了: {final}")

    if do_upload:
        click.echo(f"[6/{total}] YouTube アップロード")
        _do_upload(final, dates=[m.creation_time for m in survivors], **yt)


@click.command(name="jom-upload")
@click.argument("video", type=click.Path(exists=True, dir_okay=False, path_type=Path),
                default=DEFAULT_OUTPUT, required=False)
@youtube_options
def upload_cli(video: Path, **yt) -> None:
    """生成済みの動画を YouTube にアップロード (既定: output/jom.mp4)"""
    click.echo(f"YouTube アップロード: {video}")
    _do_upload(video, **yt)


if __name__ == "__main__":
    cli()
