#!/usr/bin/env python3
"""30周年記念映像ビルダー

  python video/scripts/build.py --res 720          # プレビュー(軽い)
  python video/scripts/build.py --res 1080         # 本番画質
  python video/scripts/build.py --res 720 --only plan   # 構成表(CSV)と警告だけ

出力: video/out/<res>p/
  rough_cut.mp4      通し映像
  digest.mp4         各パートの冒頭だけを繋いだ約3分の確認用
  rough_cut.xml      Premiere用タイムライン (ファイル > 読み込み)
  timeline.csv       タイムコード付き構成表
  contact_sheet.png  各パートのサムネイル一覧
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from graphics import FONT_JP, KIND_BG, Painter, save  # noqa: E402
from timeline import VIDEO_DIR, Timeline, build_timeline, tc  # noqa: E402
import xml_export  # noqa: E402

FPS_STR = "30000/1001"


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.stderr.write(" ".join(map(str, cmd)) + "\n" + r.stderr[-3000:])
        raise SystemExit(f"ffmpeg failed: {cmd[:6]}")
    return r


class Builder:
    def __init__(self, tl: Timeline, out: Path, quality: str):
        self.tl, self.out = tl, out.resolve()
        self.W, self.H = tl.width, tl.height
        self.p = Painter(self.W, self.H, tl.project.get("colors", {}))
        self.gfx = self.out / "graphics"
        self.clips = self.out / "clips"
        self.enc = (["-c:v", "libx264", "-preset", "veryfast", "-crf", "22"] if quality == "preview"
                    else ["-c:v", "libx264", "-preset", "medium", "-crf", "18"])
        self.enc += ["-pix_fmt", "yuv420p", "-r", FPS_STR, "-video_track_timescale", "30000"]

    # ------------------------------------------------------------ graphics
    def make_graphics(self):
        p, tl = self.p, self.tl
        for s in tl.shots:
            d, sec = s.data, s.frames / tl.fps
            path = self.gfx / f"{s.key}.png"
            if s.kind == "title":
                img = p.title_card(d.get("emoji"), d.get("heading", ""), d.get("sub", ""))
            elif s.kind == "slide_head":
                img = p.title_card(d.get("emoji"), d.get("heading", ""), "", KIND_BG["slide_head"])
            elif s.kind == "photo":
                if s.source:
                    continue
                img = p.photo_dummy(d, s.key, sec)
            elif s.kind == "intro":
                img = p.intro_card(d)
            elif s.kind == "message":
                if s.source:
                    continue
                img = p.message_dummy(d, s.key, sec)
            elif s.kind == "credits":
                img = p.credits_bg(d)
                save(p.credits_roll(d), self.gfx / f"{s.key}_roll.png")
            save(img.convert("RGB"), path)
        for o in tl.overlays:
            img = p.lower_third(o.data["name"], o.data["role"]) if o.kind == "lower_third" \
                else p.caption(o.data["text"])
            save(img, self.gfx / f"{o.key}.png")

    # ------------------------------------------------------------ clips (V1)
    def clip_path(self, s):
        return self.clips / f"{s.key}.mp4"

    def render_clip(self, s):
        tl, W, H = self.tl, self.W, self.H
        n, sec = s.frames, s.frames / tl.fps
        out = self.clip_path(s)
        png = self.gfx / f"{s.key}.png"
        still = ["-loop", "1", "-framerate", FPS_STR]
        fade = f"fade=in:st=0:d=0.5,fade=out:st={sec - 0.5:.3f}:d=0.5"
        if s.kind in ("title", "slide_head", "intro"):
            vf = fade if s.kind != "intro" else "fade=in:st=0:d=0.3"
            cmd = ["ffmpeg", "-y", *still, "-i", png, "-vf", vf]
        elif s.kind == "photo":
            src = s.source or png
            # Ken Burns: 2倍に拡大してからゆっくりズーム (交互にズームイン/アウト)
            z = f"1+0.08*on/{n}" if s.data["idx"] % 2 else f"1.08-0.08*on/{n}"
            vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                  f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS_STR},"
                  f"fade=in:st=0:d=0.4")
            cmd = ["ffmpeg", "-y", *still, "-i", src, "-vf", vf]
        elif s.kind == "message" and s.is_dummy:
            # 進行バー + 残り時間カウンター
            txt = self.clips / f"{s.key}_counter.txt"
            txt.write_text(f"残り %{{eif:trunc(({sec:.2f}-t)/60):d}}:%{{eif:mod(trunc({sec:.2f}-t),60):d:2}}",
                           encoding="utf-8")
            bx, by, bw, bh = int(360 * W / 1920), int(830 * H / 1080), int(1200 * W / 1920), max(4, int(12 * H / 1080))
            acc = "#%02x%02x%02x" % self.p.accent
            fc = (f"color=c=white@0.25:s={bw}x{bh}:r={FPS_STR},format=rgba[track];"
                  f"color=c={acc}:s={bw}x{bh}:r={FPS_STR}[bar];"
                  f"[track][bar]overlay=x='-w+w*t/{sec:.3f}':y=0:shortest=1[pb];"
                  f"[0][pb]overlay=x={bx}:y={by},"
                  f"drawtext=fontfile=ipag.ttf:textfile={txt.name}:"
                  f"fontsize={int(40 * H / 1080)}:fontcolor=white:x=w-tw-{int(60 * W / 1920)}:y={int(100 * H / 1080)}")
            cmd = ["ffmpeg", "-y", *still, "-i", png, "-filter_complex", fc]
        elif s.kind == "message":
            # 縦動画などは、ぼかした拡大映像を背景にして中央に配置
            fc = (f"[0:v]split[a][b];"
                  f"[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=20:2,"
                  f"eq=brightness=-0.15[bg];"
                  f"[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
                  f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps={FPS_STR}")
            cmd = ["ffmpeg", "-y", "-i", s.source, "-filter_complex", fc, "-an"]
        elif s.kind == "credits":
            roll = self.gfx / f"{s.key}_roll.png"
            scroll = sec - 3  # 最後の3秒は止める
            fc = (f"[0][1]overlay=x=0:y='max(H-(H+h-H*0.75)*t/{scroll:.3f}, H*0.25-h)',"
                  f"fade=in:st=0:d=0.8,fade=out:st={sec - 1.5:.3f}:d=1.5")
            cmd = ["ffmpeg", "-y", *still, "-i", png, *still, "-i", roll, "-filter_complex", fc]
        else:
            raise ValueError(s.kind)
        cwd = None
        if s.kind == "message" and s.is_dummy:
            cwd = self.clips   # drawtext には相対パスで渡す (Windows の "C:" 対策)
            font = self.clips / "ipag.ttf"
            if not font.exists():
                shutil.copy(FONT_JP, font)
        run([*map(str, cmd), "-frames:v", str(n), *self.enc, "-an", str(out.resolve())], cwd=cwd)
        return out

    def render_clips(self):
        self.clips.mkdir(parents=True, exist_ok=True)
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as ex:
            for i, _ in enumerate(ex.map(self.render_clip, self.tl.shots), 1):
                print(f"\r  clips {i}/{len(self.tl.shots)}", end="", flush=True)
        print()

    # ------------------------------------------------------------ audio
    def bgm_source(self) -> Path:
        src = self.tl.bgm.get("source")
        if src and (VIDEO_DIR / src).exists():
            return VIDEO_DIR / src
        loop = self.out / "dummy_bgm_loop.wav"
        if not loop.exists():
            # C - Am - F - G を4秒ずつ鳴らす簡易パッド (ダミーBGM)
            c = "mod(floor(t/4),4)"
            root = f"if(eq({c},0),261.63,if(eq({c},1),220.00,if(eq({c},2),174.61,196.00)))"
            third = f"if(eq({c},1),1.1892,1.2599)"
            env = "(1-exp(-mod(t,4)*4))*exp(-mod(t,4)*0.35)"
            expr = (f"0.18*{env}*(sin(2*PI*{root}*t)+0.7*sin(2*PI*{root}*{third}*t)"
                    f"+0.6*sin(2*PI*{root}*1.4983*t)+0.4*sin(PI*{root}*t))")
            run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}|{expr}':s=48000:d=16",
                 str(loop)])
        return loop

    def make_audio(self) -> Path:
        tl = self.tl
        total = tl.total_frames / tl.fps
        norm = float(tl.bgm.get("volume", 0.6))
        duck = float(tl.bgm.get("duck_volume", 0.08))
        win = tl.message_windows()
        w = "+".join(f"clip(min(t-{a - 1:.3f},{b + 1:.3f}-t),0,1)" for a, b in win) or "0"
        vol = f"({norm}-({norm - duck})*min({w},1))"
        inputs = ["-stream_loop", "-1", "-i", str(self.bgm_source())]
        fc = [f"[0:a]atrim=0:{total:.3f},aformat=sample_rates=48000:channel_layouts=stereo,"
              f"volume='{vol}':eval=frame,afade=in:d=2,afade=out:st={total - 3:.3f}:d=3,"
              f"asplit=2[bgm][bgmonly]"]
        mix = ["[bgm]"]
        k = 1
        for s in tl.shots:
            if s.kind == "message" and s.source:
                ms = int(s.start / tl.fps * 1000)
                inputs += ["-i", str(s.source)]
                fc.append(f"[{k}:a]aformat=sample_rates=48000:channel_layouts=stereo,"
                          f"loudnorm=I=-18:TP=-1.5,atrim=0:{s.frames / tl.fps:.3f},adelay={ms}|{ms}[m{k}]")
                mix.append(f"[m{k}]")
                k += 1
        fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first[aout]")
        out = self.out / "audio.wav"
        run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc), "-map", "[aout]",
             "-t", f"{total:.3f}", str(out),
             "-map", "[bgmonly]", "-t", f"{total:.3f}", str(self.out / "bgm_track.wav")])
        return out

    # ------------------------------------------------------------ assemble
    def assemble(self, audio: Path) -> Path:
        tl = self.tl
        lst = self.out / "concat.txt"
        lst.write_text("".join(f"file '{self.clip_path(s).resolve()}'\n" for s in tl.shots))
        inputs = ["-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio)]
        chain, last = [], "0:v"
        for i, o in enumerate(tl.overlays):
            inputs += ["-i", str(self.gfx / f"{o.key}.png")]
            a, b = o.start / tl.fps, (o.start + o.frames) / tl.fps
            if o.kind == "lower_third":   # 左からスライドイン/アウト
                x = f"-W*max(0,1-(t-{a:.3f})/0.5)-W*max(0,(t-{b - 0.5:.3f})/0.5)"
            else:
                x = "0"
            chain.append(f"[{last}][{i + 2}:v]overlay=x='{x}':y=0:enable='between(t,{a:.3f},{b:.3f})'[v{i}]")
            last = f"v{i}"
        script = self.out / "overlay_filter.txt"
        script.write_text(";\n".join(chain) if chain else "[0:v]null[v0]")
        last = last if chain else "v0"
        out = self.out / "rough_cut.mp4"
        run(["ffmpeg", "-y", *inputs, "-filter_complex_script", str(script), "-map", f"[{last}]",
             "-map", "1:a", *self.enc, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
             str(out)])
        return out

    def digest(self, full: Path) -> Path:
        """各パートの冒頭だけを繋いだ確認用 (約3分)"""
        tl = self.tl
        ranges = []
        for sec in tl.sections:
            a = sec["start"] / tl.fps
            length = {"title": 8, "slideshow": 14, "message": 15, "credits": 25}[sec["type"]]
            ranges.append((a, min(a + length, (sec["start"] + sec["frames"]) / tl.fps)))
        sel = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in ranges)
        out = self.out / "digest.mp4"
        run(["ffmpeg", "-y", "-i", str(full),
             "-vf", f"select='{sel}',setpts=N/FRAME_RATE/TB",
             "-af", f"aselect='{sel}',asetpts=N/SR/TB",
             *self.enc, "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)])
        return out

    def contact_sheet(self, full: Path) -> Path:
        from PIL import Image, ImageDraw
        tl = self.tl
        picks = []
        for sec in tl.sections:
            off = {"title": 4, "slideshow": 6, "message": 12, "credits": 30}[sec["type"]]
            picks.append((sec["id"], tc(sec["start"], tl.fps), sec["start"] / tl.fps + off))
        tw, th = 480, 270
        cols = 4
        rows = (len(picks) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw, rows * (th + 40)), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        tmp = self.out / "thumb.png"
        for i, (sid, t0, t) in enumerate(picks):
            run(["ffmpeg", "-y", "-ss", f"{t:.2f}", "-i", str(full), "-frames:v", "1",
                 "-vf", f"scale={tw}:{th}", str(tmp)])
            x, y = (i % cols) * tw, (i // cols) * (th + 40)
            sheet.paste(Image.open(tmp), (x, y))
            d.text((x + 10, y + th + 8), f"{t0}  {sid}", font=self.p.font(int(26 / self.p.s)),
                   fill=(255, 255, 255))
        tmp.unlink(missing_ok=True)
        out = self.out / "contact_sheet.png"
        sheet.save(out)
        return out


def write_csv(tl: Timeline, out: Path):
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["開始", "終了", "長さ", "ID", "種類", "内容", "素材"])
        for s in tl.shots:
            d = s.data
            label = {"title": d.get("heading", ""), "slide_head": d.get("heading", ""),
                     "photo": d.get("caption", ""), "intro": f"紹介カード {d.get('name', '')}",
                     "message": f"{d.get('name', '')}（{d.get('role', '')}）",
                     "credits": d.get("heading", "")}[s.kind]
            src = "-" if s.kind in ("title", "slide_head", "intro", "credits") else \
                ("ダミー" if s.is_dummy else str(s.source.relative_to(VIDEO_DIR)
                                                 if s.source.is_relative_to(VIDEO_DIR) else s.source))
            w.writerow([tc(s.start, tl.fps), tc(s.start + s.frames, tl.fps), f"{s.frames / tl.fps:.1f}秒",
                        s.key, s.kind, label, src])


def print_plan(tl: Timeline):
    print(f"\n総尺 {tc(tl.total_frames, tl.fps)}  ({tl.width}x{tl.height} 29.97fps)")
    for sec in tl.sections:
        print(f"  {tc(sec['start'], tl.fps)}  {tc(sec['frames'], tl.fps)}  {sec['id']:<8} {sec['label']}")
    for w in tl.warnings:
        print("  ⚠", w)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", type=int, default=720, choices=[480, 720, 1080])
    ap.add_argument("--only", choices=["plan", "graphics", "xml"])
    ap.add_argument("--media-root", help="XML内のパスを書き換える (例: D:/maehara30/video)")
    ap.add_argument("--config", type=Path, help="構成表 (既定: video/config/storyboard.yaml)")
    ap.add_argument("--out", type=Path, help="出力先 (既定: video/out/<res>p)")
    a = ap.parse_args()
    h = a.res
    tl = build_timeline(a.config, width=-(-h * 16 // 18) * 2, height=h) if a.config else \
        build_timeline(width=-(-h * 16 // 18) * 2, height=h)
    out = a.out or VIDEO_DIR / "out" / f"{h}p"
    out.mkdir(parents=True, exist_ok=True)
    print_plan(tl)
    write_csv(tl, out / "timeline.csv")
    if a.only == "plan":
        return
    b = Builder(tl, out, "final" if h >= 1080 else "preview")
    print("[1/6] graphics"); b.make_graphics()
    if a.only == "graphics":
        return
    if a.only != "xml":
        print("[2/6] clips"); b.render_clips()
        print("[3/6] audio"); audio = b.make_audio()
        print("[4/6] assemble"); full = b.assemble(audio)
        print("[5/6] digest / contact sheet"); b.digest(full); b.contact_sheet(full)
    print("[6/6] premiere xml")
    xml_export.write(tl, b, out / "rough_cut.xml", a.media_root)
    print(f"\n完了: {out}")


if __name__ == "__main__":
    main()
