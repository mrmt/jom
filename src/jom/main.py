"""jom CLI: assets/ を重複除去→日付降順で連結→output/"""
from __future__ import annotations

from pathlib import Path

import click

from .concat import concat
from .dedup import dedup
from .metadata import probe
from .normalize import normalize
from .overrides import load_overrides

VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".avi", ".mkv"}
OVERRIDES_FILE = "dates.txt"


def _collect(assets_dir: Path) -> list[Path]:
    return sorted(
        p for p in assets_dir.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTS
    )


@click.command()
@click.option("--assets", "assets_dir", type=click.Path(exists=True, file_okay=False, path_type=Path),
              default=Path("assets"), show_default=True)
@click.option("--work", "work_dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path("work"), show_default=True)
@click.option("--output", "output_dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path("output"), show_default=True)
@click.option("--name", default="jom.mp4", show_default=True, help="出力ファイル名")
@click.option("--skip-normalize", is_flag=True, help="正規化済みファイル(work/)を再利用")
def cli(assets_dir: Path, work_dir: Path, output_dir: Path, name: str, skip_normalize: bool) -> None:
    """assetsの動画を重複除去→日付降順で連結"""
    files = _collect(assets_dir)
    if not files:
        raise click.ClickException(f"動画無し: {assets_dir}")

    click.echo(f"[1/5] メタデータ抽出 ({len(files)}件)")
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

    click.echo(f"[2/5] 重複検出")
    survivors, dropped = dedup(metas)
    for loser, keeper in dropped:
        click.echo(f"  除外: {loser.path.name} -> 代表 {keeper.path.name}")
    click.echo(f"  {len(metas)}件 -> {len(survivors)}件")

    click.echo(f"[3/5] 日付降順ソート")
    survivors.sort(key=lambda m: m.creation_time, reverse=True)
    for m in survivors:
        click.echo(f"  {m.date_label}  {m.path.name}  ({m.width}x{m.height}, {m.duration:.1f}s)")

    click.echo(f"[4/5] 正規化+日付焼き込み")
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

    click.echo(f"[5/5] 連結")
    final = output_dir / name
    concat(normalized, final)
    click.echo(f"完了: {final}")


if __name__ == "__main__":
    cli()
