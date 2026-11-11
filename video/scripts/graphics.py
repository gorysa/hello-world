"""カード・テロップ画像の生成 (Pillow)。1920x1080基準で描き、解像度に合わせて拡縮する。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_JP = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"
FONT_EMOJI = "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"

# ダミー素材の種類ごとの背景色
KIND_BG = {
    "title": None,          # project.colors.main
    "slide_head": "#123B3A",
    "photo": "#1F4E4A",
    "intro": None,
    "message": "#2A2140",
    "credits": "#0A1428",
}


def hex2rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Painter:
    def __init__(self, width: int, height: int, colors: dict):
        self.W, self.H = width, height
        self.s = width / 1920
        self.main = hex2rgb(colors.get("main", "#0B2A5B"))
        self.accent = hex2rgb(colors.get("accent", "#E8B400"))
        self.text = hex2rgb(colors.get("text", "#FFFFFF"))

    # ---------- 基本部品 ----------
    @lru_cache(maxsize=64)
    def font(self, size: int):
        return ImageFont.truetype(FONT_JP, max(8, int(size * self.s)))

    def emoji(self, ch: str, size: int) -> Image.Image:
        ch = ch.replace("️", "")
        f = ImageFont.truetype(FONT_EMOJI, 109)
        im = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((8, 8), ch, font=f, embedded_color=True)
        im = im.crop(im.getbbox())
        px = max(8, int(size * self.s))
        r = px / max(im.size)
        return im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)

    def bg(self, color) -> Image.Image:
        c = hex2rgb(color) if isinstance(color, str) else (color or self.main)
        top = tuple(min(255, int(v * 1.25 + 10)) for v in c)
        bot = tuple(int(v * 0.55) for v in c)
        grad = Image.new("RGB", (1, 256))
        for y in range(256):
            a = y / 255
            grad.putpixel((0, y), tuple(int(top[i] * (1 - a) + bot[i] * a) for i in range(3)))
        return grad.resize((self.W, self.H)).convert("RGBA")

    def text_c(self, img, text, y, size, fill=None, stroke=0, anchor="mm", x=None):
        d = ImageDraw.Draw(img)
        d.text((self.W // 2 if x is None else x, int(y * self.s)), text, font=self.font(size),
               fill=fill or self.text, anchor=anchor,
               stroke_width=int(stroke * self.s), stroke_fill=(0, 0, 0))

    def paste_c(self, img, sub, cx, cy):
        img.alpha_composite(sub, (int(cx * self.s - sub.width / 2), int(cy * self.s - sub.height / 2)))

    def badge(self, img, text):
        """右上の DUMMY バッジ"""
        d = ImageDraw.Draw(img)
        f = self.font(28)
        w = d.textlength(text, font=f)
        pad = 14 * self.s
        x1 = self.W - 30 * self.s
        x0 = x1 - w - pad * 2
        y0, y1 = 28 * self.s, 28 * self.s + 50 * self.s
        d.rounded_rectangle((x0, y0, x1, y1), radius=10 * self.s, fill=(200, 30, 30, 230))
        d.text(((x0 + x1) / 2, (y0 + y1) / 2), text, font=f, fill=(255, 255, 255), anchor="mm")

    def frame_box(self, img, box, color=(255, 255, 255, 40), outline=(255, 255, 255, 140), dash=True):
        x0, y0, x1, y1 = [int(v * self.s) for v in box]
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.rounded_rectangle((x0, y0, x1, y1), radius=int(24 * self.s), fill=color)
        if dash:
            step, ln, w = int(28 * self.s), int(16 * self.s), max(2, int(4 * self.s))
            for x in range(x0 + 20, x1 - 20, step):
                d.line((x, y0, min(x + ln, x1), y0), fill=outline, width=w)
                d.line((x, y1, min(x + ln, x1), y1), fill=outline, width=w)
            for y in range(y0 + 20, y1 - 20, step):
                d.line((x0, y, x0, min(y + ln, y1)), fill=outline, width=w)
                d.line((x1, y, x1, min(y + ln, y1)), fill=outline, width=w)
        img.alpha_composite(layer)

    def accent_line(self, img, y, half=260):
        d = ImageDraw.Draw(img)
        d.rectangle((self.W / 2 - half * self.s, y * self.s, self.W / 2 + half * self.s, (y + 6) * self.s),
                    fill=self.accent)

    # ---------- カード ----------
    def title_card(self, emoji, heading, sub="", color=None):
        img = self.bg(color)
        if emoji:
            self.paste_c(img, self.emoji(emoji, 220), 960, 360)
        self.text_c(img, heading, 610, 120, stroke=3)
        self.accent_line(img, 700)
        if sub:
            self.text_c(img, sub, 780, 52, fill=self.accent)
        return img

    def photo_dummy(self, d, key, sec):
        img = self.bg(KIND_BG["photo"])
        self.frame_box(img, (360, 120, 1560, 840))
        self.paste_c(img, self.emoji(d.get("emoji", "📸"), 260), 960, 430)
        self.text_c(img, f"写真 {d['idx']} / {d['n']}", 680, 48, fill=(230, 230, 230))
        self.text_c(img, "（ここに写真が入ります）", 760, 36, fill=(200, 200, 200))
        self.badge(img, f"DUMMY｜{key}｜{sec:.0f}秒")
        return img

    def message_dummy(self, d, key, sec):
        sec = round(sec)
        img = self.bg(KIND_BG["message"])
        self.frame_box(img, (260, 90, 1660, 880))
        self.paste_c(img, self.emoji("👤", 300), 960, 400)
        self.paste_c(img, self.emoji("🎤", 110), 1180, 520)
        self.text_c(img, f"{d['name']} さん のメッセージ映像", 680, 56, stroke=2)
        self.text_c(img, f"{d.get('role', '')}　／　想定 {int(sec // 60)}分{int(sec % 60):02d}秒", 760, 36,
                    fill=(220, 220, 220))
        self.badge(img, f"DUMMY｜{key}｜{int(sec // 60)}:{int(sec % 60):02d}")
        return img

    def intro_card(self, d):
        img = self.bg(None)
        self.paste_c(img, self.emoji("🎤", 150), 960, 300)
        self.text_c(img, f"MESSAGE {d['no']}", 450, 48, fill=self.accent)
        self.text_c(img, d.get("role", ""), 560, 56)
        self.accent_line(img, 610, half=200)
        self.text_c(img, f"{d['name']} さん", 720, 110, stroke=3)
        return img

    def credits_bg(self, d):
        img = self.bg(KIND_BG["credits"])
        return img

    def credits_roll(self, d):
        """透明な縦長PNG (エンドロール)"""
        rows = d.get("credits", [])
        line_h = 90
        top = 300
        h = int((top + 300 + len(rows) * line_h + 500) * self.s)
        img = Image.new("RGBA", (self.W, h), (0, 0, 0, 0))
        dr = ImageDraw.Draw(img)
        if d.get("emoji"):
            em = self.emoji(d["emoji"], 160)
            img.alpha_composite(em, (int(self.W / 2 - em.width / 2), int(40 * self.s)))
        dr.text((self.W / 2, int(top * self.s)), d.get("heading", ""), font=self.font(80),
                fill=self.text, anchor="mm")
        y = top + 200
        prev_left = ""
        for left, right in rows:
            if not left and right and prev_left:   # 前行の続き (右列に揃える)
                dr.text((self.W / 2 + 40 * self.s, int(y * self.s)), right, font=self.font(48),
                        fill=self.text, anchor="lm")
                y += line_h
                continue
            prev_left = left
            if left:
                dr.text((self.W / 2 - 40 * self.s, int(y * self.s)), left, font=self.font(40),
                        fill=self.accent, anchor="rm")
            if right:
                dr.text((self.W / 2 + 40 * self.s, int(y * self.s)) if left else (self.W / 2, int(y * self.s)),
                        right, font=self.font(48 if left else 56), fill=self.text,
                        anchor="lm" if left else "mm")
            y += line_h
        # 最後に大きくチーム名
        y += 200
        dr.text((self.W / 2, int(y * self.s)), "前原ルーキーズ", font=self.font(100), fill=self.text, anchor="mm",
                stroke_width=int(3 * self.s), stroke_fill=(0, 0, 0))
        return img

    # ---------- テロップ (透過PNG, 画面全体サイズ) ----------
    def lower_third(self, name, role):
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        x0, y0, x1, y1 = 90, 820, 980, 980
        s = self.s
        d.rectangle((x0 * s, y0 * s, x1 * s, y1 * s), fill=(*self.main, 225))
        d.rectangle((x0 * s, y0 * s, (x0 + 14) * s, y1 * s), fill=self.accent)
        d.text(((x0 + 50) * s, (y0 + 48) * s), role, font=self.font(36), fill=self.accent, anchor="lm")
        d.text(((x0 + 50) * s, (y0 + 112) * s), f"{name} さん", font=self.font(64), fill=self.text, anchor="lm")
        return img

    def caption(self, text):
        img = Image.new("RGBA", (self.W, self.H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        f = self.font(52)
        w = d.textlength(text, font=f)
        cx, cy = self.W / 2, 950 * self.s
        pad = 40 * self.s
        d.rounded_rectangle((cx - w / 2 - pad, cy - 50 * self.s, cx + w / 2 + pad, cy + 50 * self.s),
                            radius=int(16 * self.s), fill=(0, 0, 0, 150))
        d.text((cx, cy), text, font=f, fill=self.text, anchor="mm")
        return img


def save(img: Image.Image, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path
