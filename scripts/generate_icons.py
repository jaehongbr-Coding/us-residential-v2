"""The Brief 앱 아이콘 생성 스크립트 (Node.js/sharp 대체 - Pillow 사용)

출력: assets/icons/icon-192.png, assets/icons/icon-512.png
디자인 기준 캔버스: 192x192 (512는 동일 비율로 스케일)
"""
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "assets", "icons")
os.makedirs(OUT_DIR, exist_ok=True)

NAVY = (27, 58, 92, 255)       # #1B3A5C
WHITE = (255, 255, 255, 255)

FONT_DIR = r"C:\Windows\Fonts"
FONT_SANS = os.path.join(FONT_DIR, "arial.ttf")
FONT_SERIF_BOLD = os.path.join(FONT_DIR, "georgiab.ttf")

BASE = 192  # 디자인 기준 캔버스 크기

# 뉴스지 텍스처: (x, y, w, h, opacity) - BASE=192 기준
TEXTURE_LINES = [
    (14, 16, 70, 3, 0.14), (100, 18, 78, 3, 0.09),
    (14, 26, 50, 3, 0.18), (78, 28, 46, 3, 0.11),
    (140, 26, 38, 3, 0.16),
    (14, 172, 60, 3, 0.10), (90, 174, 88, 3, 0.15),
    (14, 182, 90, 3, 0.08), (118, 182, 60, 3, 0.13),
]


def draw_spaced_text(draw, xy, text, font, fill, tracking, canvas, anchor_center=True):
    """letter-spacing(tracking, px)을 적용해 텍스트를 그리고 폭을 반환."""
    widths = []
    for ch in text:
        bbox = font.getbbox(ch)
        widths.append(bbox[2] - bbox[0])
    total_w = sum(widths) + tracking * (len(text) - 1 if len(text) > 1 else 0)

    cx, cy = xy
    x = cx - total_w / 2 if anchor_center else cx
    ascent, descent = font.getmetrics()
    y = cy - (ascent + descent) / 2

    for ch, w in zip(text, widths):
        draw.text((x, y), ch, font=font, fill=fill)
        x += w + tracking
    return total_w


def rounded_rect_mask(size, radius):
    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([(0, 0), (size - 1, size - 1)], radius=radius, fill=255)
    return mask


def generate(size, out_path):
    scale = size / BASE

    # 1) 배경 (navy, rounded corner)
    icon = Image.new("RGBA", (size, size), NAVY)
    radius = int(size * 0.2)
    mask = rounded_rect_mask(size, radius)
    bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    bg.paste(icon, (0, 0), mask)
    icon = bg

    draw = ImageDraw.Draw(icon, "RGBA")

    # 2) 신문 텍스처 라인 (흰색 반투명)
    for lx, ly, lw, lh, op in TEXTURE_LINES:
        x0, y0 = lx * scale, ly * scale
        x1, y1 = (lx + lw) * scale, (ly + lh) * scale
        alpha = int(255 * op)
        draw.rectangle([x0, y0, x1, y1], fill=(255, 255, 255, alpha))

    # 3) 상단 구분선 (흰색 2px)
    rule_w = 96 * scale
    rule_h = max(1, round(2 * scale))
    cx = size / 2
    top_rule_y = 66 * scale
    draw.rectangle(
        [cx - rule_w / 2, top_rule_y, cx + rule_w / 2, top_rule_y + rule_h],
        fill=WHITE,
    )

    # 4) "THE" (sans-serif, letter-spacing 4px, 16pt)
    the_font = ImageFont.truetype(FONT_SANS, int(16 * scale))
    draw_spaced_text(draw, (cx, 82 * scale), "THE", the_font, WHITE, 4 * scale, icon)

    # 5) "Brief" (Georgia bold serif, 38pt)
    brief_font = ImageFont.truetype(FONT_SERIF_BOLD, int(38 * scale))
    draw_spaced_text(draw, (cx, 118 * scale), "Brief", brief_font, WHITE, 0, icon)

    # 6) 하단 구분선 (흰색 2px)
    bottom_rule_y = 150 * scale
    draw.rectangle(
        [cx - rule_w / 2, bottom_rule_y, cx + rule_w / 2, bottom_rule_y + rule_h],
        fill=WHITE,
    )

    # 7) "WOOMI GLOBAL" (흰색 opacity 0.7, 9pt, letter-spacing 2px)
    woomi_font = ImageFont.truetype(FONT_SANS, int(9 * scale))
    woomi_fill = (255, 255, 255, int(255 * 0.7))
    draw_spaced_text(draw, (cx, 164 * scale), "WOOMI GLOBAL", woomi_font, woomi_fill, 2 * scale, icon)

    icon.save(out_path, "PNG")
    print(f"saved: {out_path} ({size}x{size})")


if __name__ == "__main__":
    generate(192, os.path.join(OUT_DIR, "icon-192.png"))
    generate(512, os.path.join(OUT_DIR, "icon-512.png"))
