"""Tạo ảnh bản đồ nền + bảng toạ độ điểm từ thư mục map của RCS (giải nén 'RTA-C060-...zip').
  pip install pillow numpy
  python build_map.py <thư_mục_chứa_topo.json_và_file_.pgm_.yaml> [hệ_số_thu_nhỏ=3]
Thường dùng update_map.py (nhận thẳng file zip). Kết quả trong thư mục map: map.png, map_meta.json, points.json. Chạy lại khi map đổi; tool đang chạy tự nạp bản đồ mới, không cần restart.
"""
import glob, json, os, re, sys, time
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))


def build(src, F=3, out=os.path.join(HERE, "map")):
    """Dựng map.png, map_meta.json, points.json từ thư mục có topo.json + .yaml + .pgm."""
    os.makedirs(out, exist_ok=True)

    yaml_f = [f for f in glob.glob(os.path.join(src, "*.yaml")) if "reloc" not in f][0]
    y = open(yaml_f, encoding="utf-8").read()
    res = float(re.search(r"^resolution:\s*([\d.]+)", y, re.M).group(1))
    ox, oy = [float(v) for v in re.search(r"^origin:\s*\[([^\]]+)\]", y, re.M).group(1).split(",")[:2]]
    pgm = yaml_f[:-5] + ".pgm"
    g = np.array(Image.open(pgm).convert("L"))
    H0, W0 = g.shape
    H, W = -(-H0 // F), -(-W0 // F)
    pad = np.full((H * F, W * F), 255, np.uint8)
    pad[:H0, :W0] = g
    blk = pad.reshape(H, F, W, F).min(axis=(1, 3))          # lấy điểm tối nhất trong khối để nét mảnh không biến mất
    base = np.where(blk < 200, 255 - (255 - blk) * 0.85, 255).astype(np.uint8)
    img = Image.fromarray(base).filter(ImageFilter.MinFilter(3)).convert("RGB")
    img = Image.eval(img, lambda v: min(255, int(v * 0.72 + 70)))   # nền xám nhạt, nét xám đậm

    step = res * F                                           # mét / pixel của ảnh xuất ra
    def to_px(xm, ym):
        return (xm - ox) / step, H - (ym - oy) / step

    topo = json.load(open(os.path.join(src, "topo.json"), encoding="utf-8"))
    pts, pos = {}, {}
    for n in topo["nodes"]:
        c = n.get("coordinate") or {}
        if "x" in c:
            pos[str(n.get("name"))] = (c["x"] / 1000.0, c["y"] / 1000.0)
            pts[str(n.get("name"))] = [c["x"], c["y"]]
            if n.get("content") not in (None, ""):
                pts.setdefault(str(n["content"]), [c["x"], c["y"]])
    # đường đi (mờ) để nhìn ra tuyến
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    seen = set()
    for n in topo["nodes"]:
        a = pos.get(str(n.get("name")))
        for e in n.get("contentEdges") or []:
            b = pos.get(str(e.get("destination")))
            k = tuple(sorted((str(n.get("name")), str(e.get("destination")))))
            if a and b and k not in seen:
                seen.add(k)
                d.line([to_px(*a), to_px(*b)], fill=(37, 99, 235, 70), width=1)
    img = Image.alpha_composite(img.convert("RGBA"), ov)
    # cắt ảnh sát vùng có node (bỏ phần trắng thừa), nhớ độ lệch để đổi toạ độ robot
    xs = [p[0] for p in pos.values()]; ys = [p[1] for p in pos.values()]
    mg = 6.0
    cx0, cy1 = to_px(min(xs) - mg, max(ys) + mg)
    cx1, cy0 = to_px(max(xs) + mg, min(ys) - mg)
    CX, CY = max(0, int(cx0)), max(0, int(cy1))
    CX1, CY1 = min(W, int(cx1)), min(H, int(cy0))
    img = img.crop((CX, CY, CX1, CY1))
    _to_px = to_px
    def to_px(xm, ym):
        a, b = _to_px(xm, ym)
        return a - CX, b - CY
    # nhãn khu
    ZONES = [("Kho 2500", -148, -57, 66, 90), ("Kho lắp ráp", -22, 48, 67, 93), ("Kho vật tư 2", 0, 38, 22, 45), ("Kho vật tư 1", -3, 39, -37, 4),
             ("Xưởng máy", 55, 105, 46, 57), ("Xưởng LED trụ", 54, 76, -23, 44), ("Kho thành phẩm", 76, 104, -23, 44), ("Khu xuất", 55, 104, -37, -28),
             ("Khu nhập", 97, 103, -73, -38), ("Cụm sạc", 27, 33, 5, 8)]
    font = None
    for fn in ("DejaVuSans-Bold.ttf", "arialbd.ttf", "segoeuib.ttf"):      # Linux / Windows; cần font có dấu tiếng Việt
        try:
            font = ImageFont.truetype(fn, max(14, int(54 / F * 1.4)))
            break
        except OSError:
            pass
    font = font or ImageFont.load_default()
    d = ImageDraw.Draw(img)
    for name, x0, x1, y0, y1 in ZONES:
        cx, cy = to_px((x0 + x1) / 2, y1 - 2.0)
        w = d.textlength(name, font=font)
        x0, y0, x1, y1 = d.textbbox((cx - w / 2, cy - 11), name, font=font)     # khung theo chữ thật (kể cả dấu tiếng Việt)
        d.rectangle([x0 - 6, y0 - 4, x1 + 6, y1 + 4], fill=(255, 255, 255, 215))
        d.text((cx - w / 2, cy - 11), name, fill=(15, 118, 110, 255), font=font)
    img.convert("RGB").save(os.path.join(out, "map.png"), optimize=True)
    with open(os.path.join(out, "points.json"), "w") as f:
        json.dump(pts, f, separators=(",", ":"))
    with open(os.path.join(out, "map_meta.json"), "w", encoding="utf-8") as f:    # ghi sau cùng: main.py thấy file này đổi thì nạp lại bản đồ
        json.dump({"w": img.size[0], "h": img.size[1], "m_per_px": step, "origin_x": ox + CX * step, "origin_y": oy + (H - CY1) * step,
                   "zones": [z[0] for z in ZONES], "built": time.strftime("%Y-%m-%d %H:%M:%S"), "source": os.path.basename(os.path.normpath(src))}, f, ensure_ascii=False)
    print("map.png", img.size, "| điểm:", len(pts))
    return img.size, len(pts)


if __name__ == "__main__":
    build(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 3)
