"""構成表(storyboard.yaml)を読み込み、タイムライン(フレーム単位)を計算する。"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

VIDEO_DIR = Path(__file__).resolve().parents[1]
CONFIG = VIDEO_DIR / "config" / "storyboard.yaml"

SLIDE_HEADING_SEC = 4.0      # スライドショー冒頭の見出しカード
DEFAULT_PHOTO_SEC = 5.0
LOWER_THIRD_SEC = 10.0       # メッセージ冒頭で名前テロップを出す秒数


def parse_time(v) -> float:
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    parts = [float(p) for p in str(v).split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def tc(frames: int, fps: float) -> str:
    """フレーム数 -> HH:MM:SS (表示用)"""
    s = round(frames / fps)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, check=True).stdout
        return float(json.loads(out)["format"]["duration"])
    except Exception:
        return None


@dataclass
class Shot:
    """V1トラックに並ぶ1カット"""
    key: str                 # 一意なキー (ファイル名にも使う)
    seg_id: str              # 所属セクションID
    kind: str                # title / slide_head / photo / intro / message / credits
    frames: int
    data: dict
    source: Path | None = None   # 本物素材 (無ければダミー)
    start: int = 0

    @property
    def is_dummy(self) -> bool:
        return self.source is None


@dataclass
class Overlay:
    """V2トラック(テロップ)"""
    key: str
    kind: str                # lower_third / caption
    start: int
    frames: int
    data: dict


@dataclass
class Timeline:
    project: dict
    fps: float
    width: int
    height: int
    shots: list[Shot] = field(default_factory=list)
    overlays: list[Overlay] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    bgm: dict = field(default_factory=dict)

    @property
    def total_frames(self) -> int:
        return sum(s.frames for s in self.shots)

    def message_windows(self) -> list[tuple[float, float]]:
        return [(s.start / self.fps, (s.start + s.frames) / self.fps)
                for s in self.shots if s.kind == "message"]


def _resolve_source(src: str | None) -> Path | None:
    if not src:
        return None
    p = Path(src)
    if not p.is_absolute():
        p = VIDEO_DIR / p
    return p if p.exists() else None


def build_timeline(config_path: Path = CONFIG, width: int | None = None,
                   height: int | None = None) -> Timeline:
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    proj = cfg["project"]
    fps = float(proj.get("fps", 29.97))
    fps = 30000 / 1001 if abs(fps - 29.97) < 0.01 else fps
    tl = Timeline(project=proj, fps=fps,
                  width=width or int(proj.get("width", 1920)),
                  height=height or int(proj.get("height", 1080)),
                  bgm=cfg.get("bgm", {}) or {})
    f = lambda sec: max(1, round(sec * fps))
    intro_sec = parse_time(cfg.get("intro_card", 8))
    target = parse_time(proj.get("target_total", "30:00"))

    # --- 1パス目: 各セクションの秒数 (flex以外) を確定 -----------------
    seq = cfg["sequence"]
    msg_no = 0
    fixed = 0.0
    plans = []
    for seg in seq:
        t = seg["type"]
        if t in ("title", "credits"):
            d = parse_time(seg["duration"])
            plans.append((seg, d)); fixed += d
        elif t == "message":
            msg_no += 1
            seg["_no"] = msg_no
            src = _resolve_source(seg.get("source"))
            d = probe_duration(src) if src else None
            if seg.get("source") and not src:
                tl.warnings.append(f"{seg['id']}: 素材 {seg['source']} が見つからないためダミー表示")
            d = d or parse_time(seg.get("duration", "5:00"))
            seg["_src"], seg["_dur"] = src, d
            plans.append((seg, intro_sec + d)); fixed += intro_sec + d
        elif t == "slideshow":
            if seg.get("flex"):
                plans.append((seg, None))
            else:
                n = len(seg["photos"])
                d = SLIDE_HEADING_SEC + n * parse_time(seg.get("seconds_per_photo", DEFAULT_PHOTO_SEC))
                plans.append((seg, d)); fixed += d
        else:
            raise ValueError(f"unknown type: {t}")

    # --- flex セクションの長さを決める --------------------------------
    flex = [p for p in plans if p[1] is None]
    remain = max(0.0, target - fixed)
    per_flex = remain / len(flex) if flex else 0
    resolved = []
    for seg, d in plans:
        if d is None:
            lo, hi = parse_time(seg.get("min", 60)), parse_time(seg.get("max", 600))
            d = min(max(per_flex, lo), hi)
            if per_flex < lo:
                tl.warnings.append(
                    f"{seg['id']}: 目標{tc(f(target), fps)}に収めるには写真パートが{per_flex:.0f}秒しか取れず、最小{lo:.0f}秒を使用 → 総尺オーバー")
        resolved.append((seg, d))

    # --- 2パス目: ショット展開 ----------------------------------------
    pos = 0

    def add(shot: Shot):
        nonlocal pos
        shot.start = pos
        tl.shots.append(shot)
        pos += shot.frames

    for seg, d in resolved:
        sid, t = seg["id"], seg["type"]
        sec_start = pos
        if t == "title":
            add(Shot(f"{sid}", sid, "title", f(d), seg))
        elif t == "credits":
            add(Shot(f"{sid}", sid, "credits", f(d), seg))
        elif t == "slideshow":
            photos = seg["photos"]
            add(Shot(f"{sid}_head", sid, "slide_head", f(SLIDE_HEADING_SEC), seg))
            total_photo = f(d) - f(SLIDE_HEADING_SEC)
            n = len(photos)
            for i, ph in enumerate(photos):
                fr = total_photo // n + (1 if i < total_photo % n else 0)
                data = dict(ph, idx=i + 1, n=n, heading=seg.get("heading", ""),
                            emoji=seg.get("emoji", "📸"))
                shot = Shot(f"{sid}_p{i + 1:02d}", sid, "photo", fr, data,
                            source=_resolve_source(ph.get("source")))
                add(shot)
                if ph.get("caption"):
                    tl.overlays.append(Overlay(f"{shot.key}_cap", "caption", shot.start, fr,
                                               {"text": ph["caption"]}))
        elif t == "message":
            no = seg["_no"]
            add(Shot(f"{sid}_intro", sid, "intro", f(intro_sec), dict(seg, no=no)))
            shot = Shot(f"{sid}", sid, "message", f(seg["_dur"]), dict(seg, no=no), source=seg["_src"])
            add(shot)
            tl.overlays.append(Overlay(f"{sid}_lt", "lower_third", shot.start,
                                       min(shot.frames, f(LOWER_THIRD_SEC)),
                                       {"name": seg["name"], "role": seg.get("role", "")}))
        tl.sections.append({"id": sid, "type": t, "start": sec_start, "frames": pos - sec_start,
                            "label": seg.get("heading") or
                            (f"{seg.get('name', '')}（{seg.get('role', '')}）" if t == "message" else sid)})

    total = tl.total_frames
    if total > f(target) + f(5):
        tl.warnings.append(f"総尺 {tc(total, fps)} が目標 {tc(f(target), fps)} を超えています")
    return tl
