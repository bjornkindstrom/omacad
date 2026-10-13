#!/usr/bin/env python3
"""YouTube thumbnail (1280x720) from a real Omacad screenshot: python video/thumbnail/make_thumbnail.py [out.png]"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "video/thumbnail/thumbnail.png"
W, H = 1280, 720
BG, TEAL, ORANGE = (18, 19, 28), (45, 212, 191), (251, 146, 60)
FONT = "/usr/share/fonts/opentype/inter/Inter-Black.otf"

img = Image.new("RGB", (W, H), BG)
glow = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(glow)
d.ellipse((560, 120, 1260, 700), fill=(20, 90, 85))
d.ellipse((-200, 500, 400, 900), fill=(90, 45, 15))
img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(140)), 0.9)

shot = Image.open(ROOT / "screenshots/1_part_tokyo-night.png").convert("RGB").crop((840, 600, 2640, 1850))
shot = shot.resize((820, int(820 * shot.height / shot.width)), Image.LANCZOS)
mask = Image.new("L", shot.size, 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, *shot.size), 28, fill=255)
mask = mask.filter(ImageFilter.GaussianBlur(1))
pos = (W - shot.width + 30, (H - shot.height) // 2 + 20)
shadow = Image.new("RGB", (W, H), (0, 0, 0)); sm = Image.new("L", (W, H), 0)
sm.paste(mask, (pos[0] + 10, pos[1] + 14)); img.paste(shadow, (0, 0), sm.filter(ImageFilter.GaussianBlur(24)))
img.paste(shot, pos, mask)

dr = ImageDraw.Draw(img)
big, small = ImageFont.truetype(FONT, 150), ImageFont.truetype(FONT, 58)
for i, (word, col) in enumerate((("NATIVE", (255, 255, 255)), ("CAD", TEAL))):
    dr.text((52, 150 + i * 150), word, font=big, fill=col, stroke_width=3, stroke_fill=(0, 0, 0))
dr.rounded_rectangle((52, 500, 560, 580), 14, fill=ORANGE)
dr.text((78, 506), "for Omarchy Linux", font=ImageFont.truetype(FONT, 46), fill=(20, 20, 20))
dr.text((52, 80), "OMACAD", font=small, fill=(200, 205, 220))
img.save(OUT)
print(OUT)
