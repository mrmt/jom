"""重複動画検出

Stage1: サイズ→SHA-256 でバイト完全一致検出
Stage2: duration近傍→数フレームpHash合成のハミング距離で再エンコード耐性検出
代表は最高解像度→次いで最大ファイルサイズを残す
"""
from __future__ import annotations

import hashlib
import subprocess
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import imagehash
from PIL import Image

from .metadata import VideoMeta

# サンプリング相対位置 (duration の割合)
SAMPLE_POINTS = (0.1, 0.3, 0.5, 0.7, 0.9)
# pHash 合計ハミング距離の閾値
PHASH_THRESHOLD = 12
# duration が同一クラスタとみなせる差 (秒)
DURATION_TOLERANCE = 0.6


def sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while buf := f.read(chunk):
            h.update(buf)
    return h.hexdigest()


def video_fingerprint(meta: VideoMeta) -> list[imagehash.ImageHash]:
    """指定位置のフレームを抽出しpHashを並べる"""
    hashes: list[imagehash.ImageHash] = []
    for p in SAMPLE_POINTS:
        t = max(0.0, min(meta.duration * p, max(0.0, meta.duration - 0.05)))
        cmd = [
            "ffmpeg", "-v", "error",
            "-ss", f"{t:.3f}",
            "-i", str(meta.path),
            "-frames:v", "1",
            "-vf", "scale=128:128:force_original_aspect_ratio=disable",
            "-f", "image2", "-vcodec", "png",
            "pipe:1",
        ]
        result = subprocess.run(cmd, capture_output=True, check=True)
        img = Image.open(BytesIO(result.stdout))
        hashes.append(imagehash.phash(img))
    return hashes


def _fp_distance(a: list[imagehash.ImageHash], b: list[imagehash.ImageHash]) -> int:
    return sum(x - y for x, y in zip(a, b))


def _better(a: VideoMeta, b: VideoMeta) -> VideoMeta:
    """代表選択: 高解像度優先→ファイルサイズ大優先"""
    if a.pixels != b.pixels:
        return a if a.pixels > b.pixels else b
    if a.path.stat().st_size != b.path.stat().st_size:
        return a if a.path.stat().st_size > b.path.stat().st_size else b
    return a


def dedup(metas: list[VideoMeta]) -> tuple[list[VideoMeta], list[tuple[VideoMeta, VideoMeta]]]:
    """重複除去。返り値 = (代表リスト, 除外ペア[除外, 残った代表])"""
    dropped: list[tuple[VideoMeta, VideoMeta]] = []

    # Stage1: SHA-256
    size_bucket: dict[int, list[VideoMeta]] = defaultdict(list)
    for m in metas:
        size_bucket[m.path.stat().st_size].append(m)

    survivors: list[VideoMeta] = []
    for bucket in size_bucket.values():
        if len(bucket) == 1:
            survivors.append(bucket[0])
            continue
        by_hash: dict[str, list[VideoMeta]] = defaultdict(list)
        for m in bucket:
            by_hash[sha256(m.path)].append(m)
        for group in by_hash.values():
            keeper = group[0]
            for other in group[1:]:
                dropped.append((other, keeper))
            survivors.append(keeper)

    # Stage2: pHash (duration近傍のみ比較)
    survivors.sort(key=lambda m: m.duration)
    fingerprints: dict[Path, list[imagehash.ImageHash]] = {}
    final: list[VideoMeta] = []
    # インデックスを残しつつ「除外印」を持つ
    dropped_paths: set[Path] = set()

    for i, m in enumerate(survivors):
        if m.path in dropped_paths:
            continue
        try:
            fp_m = fingerprints.setdefault(m.path, video_fingerprint(m))
        except Exception:
            final.append(m)
            continue
        for j in range(i + 1, len(survivors)):
            n = survivors[j]
            if n.path in dropped_paths:
                continue
            if n.duration - m.duration > DURATION_TOLERANCE:
                break
            if abs(m.duration - n.duration) > DURATION_TOLERANCE:
                continue
            try:
                fp_n = fingerprints.setdefault(n.path, video_fingerprint(n))
            except Exception:
                continue
            if _fp_distance(fp_m, fp_n) <= PHASH_THRESHOLD:
                keeper = _better(m, n)
                loser = n if keeper is m else m
                dropped.append((loser, keeper))
                dropped_paths.add(loser.path)
                if loser is m:
                    break  # mが敗者なら以降のnと比較不要
        if m.path not in dropped_paths:
            final.append(m)

    return final, dropped
