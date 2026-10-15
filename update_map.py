"""Cập nhật bản đồ của tool khi map RCS thay đổi.
  python update_map.py "docs\\3-map2 (29).zip"      -> file map xuất từ RCS (zip lồng zip cũng được) hoặc thư mục đã giải nén
  python update_map.py --rcs                        -> tải map mới nhất thẳng từ RCS (API topologyList, cần rcs_api trong config.json)
  python update_map.py <file.zip> --list            -> chỉ liệt kê các map có trong file, không cập nhật
Tuỳ chọn: --model RTA-C060 (chọn map của loại xe nào, mặc định "map_model" trong config.json), --scale 3 (hệ số thu nhỏ ảnh).
Cần: pip install pillow numpy. Bản đồ cũ được sao lưu vào map\\backup\\. Tool đang chạy tự nạp bản đồ mới (không cần restart).
"""
import argparse
import glob
import json
import os
import shutil
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8-sig"))
MAP_DIR = os.path.join(HERE, CFG.get("map_dir", "map"))
KEEP_BACKUPS = 5


def extract_all(zip_path, dest):
    """Giải nén zip, rồi giải nén tiếp các zip nằm bên trong (map RCS thường là zip lồng zip)."""
    todo = [(zip_path, dest)]
    while todo:
        z, d = todo.pop()
        os.makedirs(d, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(d)
        for inner in glob.glob(os.path.join(d, "**", "*.zip"), recursive=True):
            sub = inner[:-4]
            if not os.path.exists(sub):
                todo.append((inner, sub))


def find_maps(root):
    """Các thư mục map dựng được: có topo.json + file .yaml (không phải _reloc) + .pgm cùng tên."""
    out = []
    for topo in glob.glob(os.path.join(root, "**", "topo.json"), recursive=True):
        d = os.path.dirname(topo)
        yamls = [y for y in glob.glob(os.path.join(d, "*.yaml")) if "reloc" not in os.path.basename(y)]
        if yamls and os.path.exists(yamls[0][:-5] + ".pgm"):
            out.append(d)
    return sorted(out)


def pick(maps, model):
    hit = [m for m in maps if model and model.lower() in os.path.basename(m).lower()]
    if len(hit) >= 1:
        return hit[0]
    if len(maps) == 1:
        return maps[0]
    return None


def from_rcs(tmp):
    import rcs_api
    api = CFG.get("rcs_api") or {}
    data = rcs_api.call(api, "topology", {"areaId": int(api.get("area_id", 1))}) or {}
    url = data.get("mapZipUrl")
    if not url:
        raise SystemExit(f"RCS không trả mapZipUrl (trả về: {data})")
    print("Tải map từ RCS:", url.split("?")[0])
    p = os.path.join(tmp, "rcs_map.zip")
    with open(p, "wb") as f:
        f.write(rcs_api.download(url))
    return p, f"RCS topologyList area {api.get('area_id')} ({time.strftime('%Y-%m-%d %H:%M')})"


def backup():
    if not os.path.exists(os.path.join(MAP_DIR, "map_meta.json")):
        return None
    root = os.path.join(MAP_DIR, "backup")
    dst = os.path.join(root, time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(dst, exist_ok=True)
    for f in ("map.png", "map_meta.json", "points.json"):
        if os.path.exists(os.path.join(MAP_DIR, f)):
            shutil.copy2(os.path.join(MAP_DIR, f), dst)
    for old in sorted(os.listdir(root))[:-KEEP_BACKUPS]:
        shutil.rmtree(os.path.join(root, old), ignore_errors=True)
    return dst


def check_nodes(points):
    """Báo các ô highbay trong nodes.json không có trên bản đồ mới (tên điểm/bản đồ lệch nhau)."""
    try:
        nodes = json.load(open(os.path.join(HERE, CFG.get("nodes_file", "nodes.json")), encoding="utf-8-sig"))
    except Exception:
        return
    miss = [n["l"] for n in nodes if n.get("r") not in points and n.get("n") not in points]
    print(f"Ô highbay có toạ độ trên bản đồ: {len(nodes) - len(miss)}/{len(nodes)}")
    if miss:
        print(f"  ! {len(miss)} ô không tìm thấy trên bản đồ mới (vd. {', '.join(miss[:8])}). Kiểm tra lại file highbay (update_names.py).")


def main():
    ap = argparse.ArgumentParser(description="Cập nhật bản đồ G8 Monitor từ map RCS")
    ap.add_argument("src", nargs="?", help="file .zip map RCS hoặc thư mục đã giải nén")
    ap.add_argument("--rcs", action="store_true", help="tải map thẳng từ RCS (topologyList)")
    ap.add_argument("--model", default=CFG.get("map_model", "RTA-C060"), help="tên (một phần) map loại xe cần dùng")
    ap.add_argument("--scale", type=int, default=3, help="hệ số thu nhỏ ảnh (mặc định 3)")
    ap.add_argument("--list", action="store_true", help="chỉ liệt kê map trong file")
    a = ap.parse_args()
    if not a.src and not a.rcs:
        ap.print_help()
        sys.exit(1)

    if not a.list:
        try:
            import numpy, PIL  # noqa: F401  (build_map cần)
        except ImportError as e:
            raise SystemExit(f"Thiếu thư viện ({e.name}). Chạy: pip install pillow numpy")
    tmp = tempfile.mkdtemp(prefix="g8map_")
    try:
        if a.rcs:
            src, label = from_rcs(tmp)
        else:
            src, label = os.path.abspath(a.src), os.path.basename(os.path.normpath(a.src))
            if not os.path.exists(src):
                raise SystemExit(f"Không thấy {src}")
        root = src
        if os.path.isfile(src):
            print("Giải nén", os.path.basename(src), "...")
            root = os.path.join(tmp, "x")
            extract_all(src, root)
        maps = find_maps(root)
        if not maps:
            raise SystemExit("Không tìm thấy map dựng được (cần topo.json + .yaml + .pgm). "
                             "Nếu tải từ RCS mà thiếu ảnh nền .pgm, hãy xuất map từ RCS ra file zip rồi chạy lại với file đó.")
        print("Map có trong file:", ", ".join(os.path.basename(m) for m in maps))
        if a.list:
            return
        chosen = pick(maps, a.model)
        if not chosen:
            raise SystemExit(f"Không có map khớp '--model {a.model}'. Chọn một trong: " + ", ".join(os.path.basename(m) for m in maps))
        print("Dùng map:", os.path.basename(chosen))

        import build_map                          # cần pillow + numpy
        out = os.path.join(tmp, "out")
        build_map.build(chosen, a.scale, out)
        meta = json.load(open(os.path.join(out, "map_meta.json"), encoding="utf-8"))
        meta["source"] = f"{label} / {os.path.basename(chosen)}"
        json.dump(meta, open(os.path.join(out, "map_meta.json"), "w", encoding="utf-8"), ensure_ascii=False)

        b = backup()
        if b:
            print("Đã sao lưu bản đồ cũ vào", os.path.relpath(b, HERE))
        os.makedirs(MAP_DIR, exist_ok=True)
        for f in ("map.png", "points.json", "map_meta.json"):      # map_meta.json chép sau cùng (báo hiệu cho main.py nạp lại)
            shutil.copy2(os.path.join(out, f), os.path.join(MAP_DIR, f))
        check_nodes(json.load(open(os.path.join(MAP_DIR, "points.json"))))
        print("Xong. Tool đang chạy sẽ tự nạp bản đồ mới trong vòng 10 giây; tải lại trang web để thấy.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
