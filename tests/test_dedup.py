from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from jom.dedup import _better, dedup, sha256, video_fingerprint, _fp_distance
from jom.metadata import probe


def test_sha256_matches_openssl(red: Path):
    got = sha256(red)
    ref = subprocess.check_output(["shasum", "-a", "256", str(red)], text=True).split()[0]
    assert got == ref


def test_better_prefers_higher_resolution(red: Path, portrait: Path):
    m_red = probe(red)          # 320x240 = 76800
    m_por = probe(portrait)     # 240x320 = 76800 → 同じpixel数
    # 同pixelならファイルサイズ大きい方
    winner = _better(m_red, m_por)
    assert winner.path.stat().st_size >= min(
        m_red.path.stat().st_size, m_por.path.stat().st_size
    )


def test_fingerprint_same_video_zero_distance(red: Path):
    m = probe(red)
    fp1 = video_fingerprint(m)
    fp2 = video_fingerprint(m)
    assert _fp_distance(fp1, fp2) == 0


def test_fingerprint_different_videos_large_distance(red: Path, green: Path):
    fp_r = video_fingerprint(probe(red))
    fp_g = video_fingerprint(probe(green))
    # 単色の別動画なら十分離れる
    assert _fp_distance(fp_r, fp_g) > 12


def test_dedup_detects_exact_copy(tmp_path: Path, red: Path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    shutil.copy(red, a)
    shutil.copy(red, b)
    metas = [probe(a), probe(b)]
    survivors, dropped = dedup(metas)
    assert len(survivors) == 1
    assert len(dropped) == 1
    loser, keeper = dropped[0]
    assert {loser.path, keeper.path} == {a, b}


def test_dedup_keeps_distinct_videos(tmp_path: Path, red: Path, green: Path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mp4"
    shutil.copy(red, a)
    shutil.copy(green, b)
    survivors, dropped = dedup([probe(a), probe(b)])
    assert len(survivors) == 2
    assert dropped == []


def test_dedup_detects_reencoded_copy(tmp_path: Path, red: Path):
    """再エンコードしてもpHashで検出できる"""
    orig = tmp_path / "orig.mp4"
    reenc = tmp_path / "reenc.mp4"
    shutil.copy(red, orig)
    # ビットレート下げて再エンコード → ハッシュは変わる
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-i", str(orig),
        "-c:v", "libx264", "-crf", "35", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "64k",
        str(reenc),
    ], check=True)
    assert sha256(orig) != sha256(reenc)
    survivors, dropped = dedup([probe(orig), probe(reenc)])
    assert len(survivors) == 1
    assert len(dropped) == 1
