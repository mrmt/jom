from __future__ import annotations

from pathlib import Path

from PIL import Image

from jom.metadata import probe
from jom.normalize import TARGET_H, TARGET_W, make_date_png, normalize


def test_make_date_png_produces_rgba_with_text(tmp_path: Path):
    out = tmp_path / "d.png"
    make_date_png("2025-01-15 12:34", out)
    img = Image.open(out)
    assert img.mode == "RGBA"
    assert img.width > 40 and img.height > 20
    # 半透明黒背景セルが存在 (α=128)
    alphas = {img.getpixel((0, 0))[3], img.getpixel((img.width - 1, 0))[3]}
    assert 128 in alphas


def test_normalize_landscape_produces_1080p(tmp_path: Path, red: Path):
    out = tmp_path / "out.mp4"
    normalize(probe(red), out)
    m = probe(out)
    assert m.width == TARGET_W
    assert m.height == TARGET_H
    assert m.vcodec == "h264"


def test_normalize_portrait_letterboxed_to_1080p(tmp_path: Path, portrait: Path):
    out = tmp_path / "portrait_out.mp4"
    normalize(probe(portrait), out)
    m = probe(out)
    assert m.width == TARGET_W
    assert m.height == TARGET_H


def test_normalize_handles_video_without_audio(tmp_path: Path, noaudio: Path):
    """音声無し動画でも失敗せず、無音aacが付与される"""
    out = tmp_path / "no_audio_out.mp4"
    normalize(probe(noaudio), out)
    import subprocess
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=codec_name", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    )
    assert "aac" in result.stdout


def test_normalize_cleans_up_overlay_png(tmp_path: Path, red: Path):
    out = tmp_path / "out.mp4"
    normalize(probe(red), out)
    assert not out.with_suffix(".date.png").exists()
