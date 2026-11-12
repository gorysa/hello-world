#!/usr/bin/env python3
"""ローカル環境チェック: python video/scripts/doctor.py"""
import shutil
import subprocess
import sys
from pathlib import Path

ok = True


def check(name, cond, hint=""):
    global ok
    print(f"  {'OK ' if cond else 'NG '} {name}" + ("" if cond else f"  → {hint}"))
    ok &= bool(cond)


print("環境チェック")
check(f"Python {sys.version.split()[0]} (3.9以上)", sys.version_info >= (3, 9), "Python 3.9以上を入れてください")
for mod, pkg in (("yaml", "pyyaml"), ("PIL", "pillow")):
    try:
        __import__(mod)
        check(pkg, True)
    except ImportError:
        check(pkg, False, f"pip install {pkg}")
for exe in ("ffmpeg", "ffprobe"):
    check(exe, shutil.which(exe),
          "Windows: winget install Gyan.FFmpeg / Mac: brew install ffmpeg (入れたらターミナルを開き直す)")
if shutil.which("ffmpeg"):
    out = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    check("ffmpeg drawtext フィルタ", " drawtext " in out, "freetype 付きの ffmpeg (Gyan.FFmpeg / brew 版) を使ってください")
fonts = Path(__file__).resolve().parents[1] / "assets" / "fonts"
for f in ("ipag.ttf", "NotoColorEmoji.ttf"):
    check(f"フォント {f}", (fonts / f).exists(), "git pull し直してください")
try:
    from PIL import ImageFont, features
    check("Pillow 複雑テキスト (raqm)", features.check("raqm"), "無くても動作しますが絵文字が崩れたら pip install -U pillow")
    ImageFont.truetype(str(fonts / "NotoColorEmoji.ttf"), 109)
    check("カラー絵文字の読み込み", True)
except Exception as e:  # noqa: BLE001
    check("カラー絵文字の読み込み", False, str(e))
print("\nすべてOK。 python video/scripts/build.py --only plan から始めてください。" if ok else "\nNG の項目を直してから再実行してください。")
sys.exit(0 if ok else 1)
