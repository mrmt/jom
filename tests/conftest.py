"""テスト用の小さな動画をffmpegで合成"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _synth(path: Path, *, seconds: float, width: int, height: int, source: str,
           freq: int = 440, fps: int = 30) -> Path:
    """sourceにはlavfiのvideo source (color=red, testsrc, mandelbrot等) を渡す"""
    path.parent.mkdir(parents=True, exist_ok=True)
    # 全source共通で使えるs/rのみ埋め込み、durationは-tで外部指定
    sep = ":" if "=" in source else "="
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-t", str(seconds), "-i",
        f"{source}{sep}s={width}x{height}:r={fps}",
        "-f", "lavfi", "-t", str(seconds), "-i",
        f"sine=frequency={freq}:sample_rate=48000",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        "-c:a", "aac", "-shortest",
        "-metadata", "creation_time=2025-01-15T12:00:00.000000Z",
        str(path),
    ]
    subprocess.run(cmd, check=True)
    return path


@pytest.fixture(scope="session")
def synth_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("synth")
    # pHashで区別可能なようにパターン系を使う (単色はDCTが同一になる)
    _synth(d / "red.mp4", seconds=1.0, width=320, height=240, source="testsrc", freq=440)
    _synth(d / "green.mp4", seconds=1.0, width=320, height=240, source="mandelbrot", freq=660)
    _synth(d / "portrait.mp4", seconds=1.0, width=240, height=320, source="smptebars", freq=550)
    _synth(d / "silent.mp4", seconds=0.5, width=160, height=120, source="color=c=black", freq=1)
    # silentはaudio付きだが、明示的にaudio無しも作る
    subprocess.run([
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", "color=c=white:s=160x120:d=0.5:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
        str(d / "noaudio.mp4"),
    ], check=True)
    return d


@pytest.fixture
def red(synth_dir: Path) -> Path:
    return synth_dir / "red.mp4"


@pytest.fixture
def green(synth_dir: Path) -> Path:
    return synth_dir / "green.mp4"


@pytest.fixture
def portrait(synth_dir: Path) -> Path:
    return synth_dir / "portrait.mp4"


@pytest.fixture
def noaudio(synth_dir: Path) -> Path:
    return synth_dir / "noaudio.mp4"
