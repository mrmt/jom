"""1920x1080/30fps/h264/aacに正規化し、下中央に日付テロップを焼き込む

Homebrewのffmpegはdrawtext未対応(freetype無し)なので、Pillowで日付PNGを生成し
ffmpegのoverlayフィルタで合成する
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .metadata import VideoMeta

TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
_FONT_SIZE = 40
_PAD_X = 20
_PAD_Y = 10
_BOTTOM_MARGIN = 30
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/SFNS.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for p in _FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_date_png(text: str, out_path: Path) -> Path:
    """半透明黒背景+白文字の日付PNGを生成"""
    font = _load_font(_FONT_SIZE)
    tmp = Image.new("RGBA", (10, 10))
    bbox = ImageDraw.Draw(tmp).textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    w = tw + _PAD_X * 2
    h = th + _PAD_Y * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 128))
    ImageDraw.Draw(img).text((_PAD_X - bbox[0], _PAD_Y - bbox[1]), text, font=font,
                             fill=(255, 255, 255, 255))
    img.save(out_path)
    return out_path


def _has_audio(path: Path) -> bool:
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return "audio" in result.stdout


# HDR判定に使うtransferタグ
_HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}


def _probe_color(path: Path) -> dict[str, str]:
    """映像ストリームのcolor_*タグを取得"""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=color_primaries,color_transfer,color_space,color_range",
        "-of", "default=nw=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    out: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            if v and v != "unknown" and v != "N/A":
                out[k] = v
    return out


def _ffmpeg_has_filter(name: str) -> bool:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"],
        capture_output=True, text=True, check=True,
    )
    return any(line.split()[1:2] == [name] for line in result.stdout.splitlines() if line.strip())


_HAS_ZSCALE = _ffmpeg_has_filter("zscale")


def _colorspace_prefilter(color: dict[str, str]) -> str | None:
    """入力色空間に応じてBT.709/tv-rangeへの変換フィルタを返す

    - HDR (HLG/PQ) : zscale が使えるならトーンマップしてSDR化。無ければ None を返し、
      呼び出し側で警告を出す (発色は崩れたまま)
    - BT.2020 SDR : colorspace フィルタでBT.709へ変換
    - BT.709 SDR : 変換不要 (None)
    """
    transfer = color.get("color_transfer", "")
    space = color.get("color_space", "")
    primaries = color.get("color_primaries", "")
    is_hdr = transfer in _HDR_TRANSFERS
    is_bt2020 = space.startswith("bt2020") or primaries == "bt2020"

    if is_hdr:
        if not _HAS_ZSCALE:
            return None
        # HLG/PQ → linear → tonemap → BT.709 tv
        return (
            "zscale=t=linear:npl=100,format=gbrpf32le,"
            "zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
            "zscale=t=bt709:m=bt709:r=tv"
        )
    if is_bt2020:
        return "colorspace=all=bt709:iall=bt2020:range=tv:irange=tv:fast=1"
    return None


def normalize(meta: VideoMeta, out_path: Path) -> Path:
    """meta.pathを正規化して out_path に書き出す"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    overlay_png = out_path.with_suffix(".date.png")
    make_date_png(meta.date_label, overlay_png)

    has_audio = _has_audio(meta.path)
    color = _probe_color(meta.path)
    prefilter = _colorspace_prefilter(color)
    if color.get("color_transfer") in _HDR_TRANSFERS and not _HAS_ZSCALE:
        import sys
        print(
            f"WARN: {meta.path.name} はHDR ({color['color_transfer']}) だが "
            "ffmpegに zscale が無いためSDR変換不可。発色が崩れる可能性あり。"
            " `brew tap homebrew-ffmpeg/ffmpeg && "
            "brew install homebrew-ffmpeg/ffmpeg/ffmpeg` で導入可",
            file=sys.stderr,
        )
    vchain = []
    if prefilter:
        vchain.append(prefilter)
    vchain += [
        f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease",
        f"pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:color=black",
        "setsar=1",
        f"fps={TARGET_FPS}",
        "format=yuv420p",
    ]
    filter_complex = (
        f"[0:v]" + ",".join(vchain) + "[bg];"
        f"[bg][1:v]overlay=(W-w)/2:H-h-{_BOTTOM_MARGIN}[v]"
    )
    cmd: list[str] = [
        "ffmpeg", "-y", "-v", "error",
        "-i", str(meta.path),
        "-i", str(overlay_png),
    ]
    if not has_audio:
        cmd += ["-f", "lavfi", "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000", "-shortest"]
    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-map", ("2:a:0" if not has_audio else "0:a:0"),
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-pix_fmt", "yuv420p",
        # 全クリップをBT.709 tv-rangeに明示タグ付け(concat後のプレイヤー解釈揺れ防止)
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-colorspace", "bt709",
        "-color_range", "tv",
        "-r", str(TARGET_FPS),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)
    overlay_png.unlink(missing_ok=True)
    return out_path
