"""Premiere Pro 用 FCP7 XML (xmeml v4) の書き出し

トラック構成
  V1: 本編カット (写真/メッセージ/タイトル)
  V2: テロップ (名前・写真キャプション, 透過PNG)
  A1: メッセージ音声 (本物素材がある場合)
  A2: BGM (メッセージ中は自動で下げた状態)
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape

from timeline import VIDEO_DIR, Timeline, probe_duration


def _url(path: Path, media_root: str | None) -> str:
    path = Path(path).resolve()
    if media_root:
        try:
            rel = path.relative_to(VIDEO_DIR).as_posix()
        except ValueError:
            rel = path.name
        p = media_root.rstrip("/\\").replace("\\", "/") + "/" + rel
    else:
        p = path.as_posix()
    if len(p) > 1 and p[1] == ":":           # Windows ドライブ
        p = "/" + p[0] + "%3a" + quote(p[2:])
        return "file://localhost" + p
    return "file://localhost" + quote(p)


RATE = "<rate><timebase>30</timebase><ntsc>TRUE</ntsc></rate>"


class Writer:
    def __init__(self, tl: Timeline, media_root):
        self.tl, self.root = tl, media_root
        self.files: dict[str, str] = {}
        self.n = 0

    def file_el(self, path: Path, frames: int, video=True, audio=False):
        key = str(path)
        if key in self.files:
            return f'<file id="{self.files[key]}"/>'
        fid = f"file-{len(self.files) + 1}"
        self.files[key] = fid
        media = ""
        if video:
            media += (f"<video><samplecharacteristics>{RATE}<width>{self.tl.width}</width>"
                      f"<height>{self.tl.height}</height></samplecharacteristics></video>")
        if audio:
            media += ("<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate>"
                      "</samplecharacteristics><channelcount>2</channelcount></audio>")
        return (f'<file id="{fid}"><name>{escape(Path(path).name)}</name>'
                f"<pathurl>{_url(path, self.root)}</pathurl>{RATE}<duration>{frames}</duration>"
                f"<media>{media}</media></file>")

    def clip(self, name, path, start, frames, file_frames, in_=0, video=True, audio=False,
             mediatype="video", track_index=1):
        self.n += 1
        src = (f"<sourcetrack><mediatype>{mediatype}</mediatype><trackindex>{track_index}</trackindex>"
               f"</sourcetrack>" if mediatype == "audio" else "")
        return (f'<clipitem id="clipitem-{self.n}"><name>{escape(name)}</name><enabled>TRUE</enabled>'
                f"<duration>{file_frames}</duration>{RATE}<start>{start}</start><end>{start + frames}</end>"
                f"<in>{in_}</in><out>{in_ + frames}</out>"
                f"{self.file_el(path, file_frames, video, audio)}{src}</clipitem>")


def write(tl: Timeline, builder, out: Path, media_root: str | None = None):
    w = Writer(tl, media_root)
    fps = tl.fps
    v1, v2, a1, a2 = [], [], [], []
    for s in tl.shots:
        name = f"{s.key}{' [DUMMY]' if s.is_dummy and s.kind in ('photo', 'message') else ''}"
        if s.kind == "message" and s.source:
            ff = round((probe_duration(s.source) or s.frames / fps) * fps)
            v1.append(w.clip(name, s.source, s.start, s.frames, ff, video=True, audio=True))
            a1.append(w.clip(name, s.source, s.start, s.frames, ff, video=True, audio=True,
                             mediatype="audio"))
        else:
            v1.append(w.clip(name, builder.clip_path(s), s.start, s.frames, s.frames))
    for o in tl.overlays:
        png = builder.gfx / f"{o.key}.png"
        v2.append(w.clip(o.key, png, o.start, o.frames, o.frames))
    total = tl.total_frames
    bgm = builder.out / "bgm_track.wav"
    a2.append(w.clip("BGM", bgm, 0, total, total, video=False, audio=True, mediatype="audio"))

    def track(items):
        return "<track>" + "".join(items) + "</track>"

    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4">'
           f'<sequence id="sequence-1"><name>{escape(tl.project.get("title", ""))} 叩き台</name>'
           f"<duration>{total}</duration>{RATE}"
           "<timecode><rate><timebase>30</timebase><ntsc>TRUE</ntsc></rate><string>00;00;00;00</string>"
           "<frame>0</frame><displayformat>DF</displayformat></timecode>"
           "<media><video><format><samplecharacteristics>"
           f"{RATE}<width>{tl.width}</width><height>{tl.height}</height>"
           "<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance>"
           "</samplecharacteristics></format>"
           f"{track(v1)}{track(v2)}</video>"
           "<audio><numOutputChannels>2</numOutputChannels>"
           f"{track(a1)}{track(a2)}</audio></media></sequence></xmeml>\n")
    out.write_text(xml, encoding="utf-8")
    return out
