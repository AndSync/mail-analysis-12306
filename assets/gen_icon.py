"""生成 mail-analysis-12306 插件图标 v5（Pillow）
构图（标准 App 图标式）：
  主体 = 蓝色渐变徽章 + 白色高铁车头正面（深蓝风挡/红色饰带/黄色车灯）+ 铁轨 + 12306
  右上角 = 红色圆形"新邮件"角标（白色信封 + 浅蓝封舌），与车头轻微叠压，寓意 12306 邮件提醒。
4x 超采样 + LANCZOS，输出 icon.png(512)/icon-128.png/icon.svg。"""
from PIL import Image, ImageDraw, ImageFont

S = 4
W = 512 * S

BG_TOP = (61, 123, 253)
BG_BOT = (29, 78, 216)
WHITE = (255, 255, 255)
FLAP = (185, 210, 254)
NAVY = (22, 51, 110)
RED = (245, 69, 92)
LIGHT = (255, 211, 77)
RAIL = (190, 214, 255)


def sc(*vals):
    return [v * S for v in vals]


def rounded(d, x0, y0, x1, y1, r, fill, top=False):
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill,
                        corners=(True, True, False, False) if top else None)


def build(size_out):
    img = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ---- 徽章背景（垂直渐变圆角方块）----
    badge = Image.new('RGBA', (W, W), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    mask = Image.new('L', (W, W), 0)
    ImageDraw.Draw(mask).rounded_rectangle(sc(16, 16, 496, 496), radius=96 * S, fill=255)
    for y in range(W):
        t = y / W
        c = tuple(int(BG_TOP[i] + (BG_BOT[i] - BG_TOP[i]) * t) for i in range(3)) + (255,)
        bd.line([(0, y), (W, y)], fill=c)
    img.paste(badge, (0, 0), mask)

    # ---- 高铁车头正面（主体，整体左移给角标让位）----
    rounded(d, *sc(120, 100, 360, 296), r=118 * S, fill=WHITE, top=True)
    rounded(d, *sc(158, 128, 322, 206), r=38 * S, fill=NAVY, top=True)      # 风挡
    rounded(d, *sc(120, 224, 360, 242), r=9 * S, fill=RED)                  # 红色饰带
    for cx in (164, 316):                                                   # 车灯
        d.ellipse(sc(cx - 13, 258, cx + 13, 284), fill=LIGHT)
    rounded(d, *sc(106, 318, 374, 328), r=5 * S, fill=RAIL)                 # 铁轨
    rounded(d, *sc(142, 340, 338, 350), r=5 * S, fill=RAIL)

    # ---- "12306" 字样 ----
    text = '12306'
    try:
        font = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 80 * S)
    except OSError:
        font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 80 * S)
    gap = 9 * S
    widths = []
    for ch in text:
        bb = font.getbbox(ch)
        widths.append(bb[2] - bb[0])
    total = sum(widths) + gap * (len(text) - 1)
    x = (W - total) // 2
    y_top = 368 * S
    for ch, w in zip(text, widths):
        bb = font.getbbox(ch)
        d.text((x - bb[0], y_top), ch, font=font, fill=WHITE)
        x += w + gap

    # ---- 右上角红色圆形"新邮件"角标（叠压车头右上肩）----
    cx, cy, r = 412, 98, 74
    d.ellipse(sc(cx - r, cy - r, cx + r, cy + r), fill=RED)
    # 白色迷你信封
    rounded(d, *sc(cx - 36, cy - 26, cx + 36, cy + 26), r=8 * S, fill=WHITE)
    d.polygon(sc(cx - 32, cy - 22, cx, cy + 4, cx + 32, cy - 22), fill=FLAP)
    for x0 in (cx - 32, cx + 32):
        d.line(sc(x0, cy - 22, cx, cy + 4), fill=WHITE, width=int(2.5 * S))

    return img.resize((size_out, size_out), Image.LANCZOS)


SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#3D7BFD"/>
      <stop offset="1" stop-color="#1D4ED8"/>
    </linearGradient>
  </defs>
  <rect x="16" y="16" width="480" height="480" rx="96" fill="url(#bg)"/>
  <path d="M120 218 Q120 100 240 100 Q360 100 360 218 L360 296 L120 296 Z" fill="#FFFFFF"/>
  <path d="M158 166 Q158 128 196 128 L284 128 Q322 128 322 166 L322 206 L158 206 Z" fill="#16336E"/>
  <rect x="120" y="224" width="240" height="18" rx="9" fill="#F5455C"/>
  <circle cx="164" cy="271" r="13" fill="#FFD34D"/>
  <circle cx="316" cy="271" r="13" fill="#FFD34D"/>
  <rect x="106" y="318" width="268" height="10" rx="5" fill="#BED6FF"/>
  <rect x="142" y="340" width="196" height="10" rx="5" fill="#BED6FF"/>
  <text x="256" y="448" font-family="Arial, Helvetica, sans-serif" font-size="80" font-weight="bold"
        fill="#FFFFFF" text-anchor="middle" letter-spacing="7">12306</text>
  <circle cx="412" cy="98" r="74" fill="#F5455C"/>
  <rect x="376" y="72" width="72" height="52" rx="8" fill="#FFFFFF"/>
  <path d="M380 76 L412 102 L444 76 Z" fill="#B9D2FE"/>
  <line x1="380" y1="76" x2="412" y2="102" stroke="#FFFFFF" stroke-width="4"/>
  <line x1="444" y1="76" x2="412" y2="102" stroke="#FFFFFF" stroke-width="4"/>
</svg>
'''

if __name__ == '__main__':
    # 输出到本脚本所在目录（assets/），保证从任意 cwd 运行结果一致
    import os
    out_dir = os.path.dirname(os.path.abspath(__file__))
    build(512).save(os.path.join(out_dir, 'icon.png'))
    build(128).save(os.path.join(out_dir, 'icon-128.png'))
    with open(os.path.join(out_dir, 'icon.svg'), 'w', encoding='utf-8') as f:
        f.write(SVG)
    print('icon.png / icon-128.png / icon.svg written to', out_dir)
