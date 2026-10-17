"""Cập nhật tên điểm (ô highbay) từ file Excel -> nodes.json.
  python update_names.py "raw\\G8_mapping_Node_Highbay_20261007.xlsx"
  python update_names.py <file.xlsx> --check       -> chỉ kiểm tra, báo khác biệt, không ghi
Sheet đầu tiên, dòng 1 là tiêu đề. Nhận 2 dạng file:
  - File vị trí xuất từ RCS (cột Area Name, Location Code, Node; mỗi dòng một ô-tầng, vd. E40-1-1).
  - File mapping (cột Khu, Dãy, Node, Tên RCS, Tầng 1..Tầng 4).
Cả hai đều THAY TOÀN BỘ nodes.json (mỗi lần tải lên là bảng đầy đủ, mới nhất).
Cần: pip install openpyxl. nodes.json cũ được sao lưu thành nodes.json.bak. Tool đang chạy tự nạp lại (không cần restart).
"""
import argparse
import json
import os
import re
import shutil
import sys
import warnings
from collections import Counter, OrderedDict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # thư mục gốc project
sys.path.insert(0, os.path.join(ROOT, "src"))
import cfg  # noqa: E402

CFG = cfg.load()                                                     # config.example.json + config.json của máy
OUT = os.path.join(ROOT, CFG.get("nodes_file", "data/nodes.json"))
COLS = {"k": "khu", "d": "dãy", "n": "node", "r": "tên rcs"}           # khóa trong nodes.json -> đầu cột Excel (khớp phần đầu, không phân biệt hoa thường)
LEVELS = ["tầng 1", "tầng 2", "tầng 3", "tầng 4"]


def cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def read_xlsx(path):
    """Trả về (nodes, số dòng bỏ qua, kiểu file "mapping" | "rcs")."""
    import openpyxl
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                    # "Workbook contains no default style" của file xuất từ RCS
        wb = openpyxl.load_workbook(path, data_only=True)  # không dùng read_only: file RCS khai sai kích thước sheet -> chỉ đọc được 1 cột
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    head = [cell(h).lower() for h in next(rows)]

    def col(name, need=True):
        for i, h in enumerate(head):
            if h == name or h.startswith(name + " ") or h.startswith(name + "("):
                return i
        if need:
            raise SystemExit(f"Sheet '{ws.title}' thiếu cột '{name}'. Các cột đang có: {head}\n"
                             "Cần file mapping (Khu, Dãy, Node, Tên RCS, Tầng 1-4) hoặc file vị trí xuất từ RCS (Area Name, Location Code, Node).")
        return None

    nodes, skipped = [], 0
    if col("location code", False) is not None:            # file vị trí xuất từ RCS: gom các ô-tầng theo node
        ia, ic, inode = col("area name"), col("location code"), col("node")
        by = OrderedDict()
        for row in rows:
            row = list(row) + [None] * (len(head) - len(row))
            code, node = cell(row[ic]), cell(row[inode])
            if not code or not node:
                skipped += 1 if any(cell(v) for v in row) else 0
                continue
            n = by.setdefault(node, {"n": node, "r": "", "k": cell(row[ia]), "d": code.split("-")[0], "l": re.sub(r"-\d+$", "", code), "t": []})
            if code not in n["t"]:
                n["t"].append(code)
        for n in by.values():
            n["t"].sort(key=lambda t: [int(x) if x.isdigit() else x for x in t.split("-")])
            n["l"] = re.sub(r"-\d+$", "", n["t"][0])
            nodes.append(n)
        return nodes, skipped, "rcs"

    idx = {k: col(v) for k, v in COLS.items()}
    lv = [col(v) for v in LEVELS]
    for row in rows:
        row = list(row) + [None] * (len(head) - len(row))
        n = {k: cell(row[i]) for k, i in idx.items()}
        t = [cell(row[i]) for i in lv if cell(row[i])]
        if not n["n"] or not t:
            skipped += 1 if any(cell(v) for v in row) else 0
            continue
        n["l"] = re.sub(r"-\d+$", "", t[0])                # D32-1-1 -> D32-1 (nhãn ô, bỏ số tầng)
        n["t"] = t
        nodes.append({k: n[k] for k in ("n", "r", "k", "d", "l", "t")})
    return nodes, skipped, "mapping"


def validate(nodes):
    warn = []
    for key, label in (("n", "Node"), ("r", "Tên RCS")):
        dup = [v for v, c in Counter(x[key] for x in nodes if x[key]).items() if c > 1]
        if dup:
            warn.append(f"{label} trùng: {', '.join(dup[:10])}" + (" ..." if len(dup) > 10 else ""))
    dup = [v for v, c in Counter(t.upper() for x in nodes for t in x["t"]).items() if c > 1]
    if dup:
        warn.append(f"Tên vị trí (tầng) trùng: {', '.join(dup[:10])}" + (" ..." if len(dup) > 10 else ""))
    no_r = [x["n"] for x in nodes if not x["r"]]
    if no_r and not all(not x["r"] for x in nodes):       # file RCS không có Tên RCS: bỏ qua cảnh báo
        warn.append(f"{len(no_r)} dòng thiếu Tên RCS (vd. {', '.join(no_r[:5])})")
    try:
        pts = json.load(open(os.path.join(ROOT, CFG.get("map_dir", "data/map"), "points.json")))
        miss = [x["l"] for x in nodes if x["r"] not in pts and x["n"] not in pts]
        print(f"Ô có toạ độ trên bản đồ hiện tại: {len(nodes) - len(miss)}/{len(nodes)}")
        if miss:
            warn.append(f"{len(miss)} ô chưa có trên bản đồ hiện tại (vd. {', '.join(miss[:8])}). Bản đồ tool có thể cũ: bấm 'Cập nhật map từ RCS' "
                        "rồi tải lại file này; vẫn thiếu thì kiểm tra mã Node")
    except Exception:
        pass
    return warn


def diff(old, new):
    o, n = {x["n"]: x for x in old}, {x["n"]: x for x in new}
    added = [k for k in n if k not in o]
    removed = [k for k in o if k not in n]
    changed = [k for k in n if k in o and n[k] != o[k]]
    return added, removed, changed


def main():
    ap = argparse.ArgumentParser(description="Cập nhật tên điểm highbay (nodes.json) từ file Excel")
    ap.add_argument("xlsx")
    ap.add_argument("--check", action="store_true", help="chỉ kiểm tra, không ghi nodes.json")
    a = ap.parse_args()
    if not os.path.exists(a.xlsx):
        raise SystemExit(f"Không thấy {a.xlsx}")
    nodes, skipped, kind = read_xlsx(a.xlsx)
    if not nodes:
        raise SystemExit("Không đọc được dòng nào (cần cột Node và tên ô).")
    print(f"Đọc {len(nodes)} điểm ({sum(len(x['t']) for x in nodes)} ô-tầng) từ {os.path.basename(a.xlsx)}"
          + (" - file vị trí xuất từ RCS" if kind == "rcs" else " - file mapping") + (f" (bỏ qua {skipped} dòng thiếu dữ liệu)" if skipped else ""))
    print("Theo khu:", ", ".join(f"{k} {v}" for k, v in Counter(x["k"] for x in nodes).most_common()))
    print("Dãy:", ", ".join(f"{k} {v}" for k, v in sorted(Counter(x["d"] for x in nodes).items())))
    for w in validate(nodes):
        print("  !", w)
    try:
        old = json.load(open(OUT, encoding="utf-8-sig"))
    except Exception:
        old = []
    print(f"Thay toàn bộ bảng hiện tại ({len(old)} điểm) bằng {len(nodes)} điểm trong file.")
    added, removed, changed = diff(old, nodes)
    if not (added or removed or changed):
        print("Không có thay đổi so với nodes.json hiện tại.")
        return
    lbl = lambda src, ks: ", ".join(src[k]["l"] for k in ks[:8]) + (" ..." if len(ks) > 8 else "")
    o, n = {x["n"]: x for x in old}, {x["n"]: x for x in nodes}
    if added:
        print(f"Thêm {len(added)}: {lbl(n, added)}")
    if removed:
        print(f"Bỏ {len(removed)}: {lbl(o, removed)}")
    if changed:
        print(f"Đổi {len(changed)}: " + ", ".join(f"{o[k]['l']}->{n[k]['l']}" if o[k]["l"] != n[k]["l"] else n[k]["l"] for k in changed[:8])
              + (" ..." if len(changed) > 8 else ""))
    if a.check:
        print("(--check: chưa ghi gì)")
        return
    if os.path.exists(OUT):
        shutil.copy2(OUT, OUT + ".bak")
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(nodes, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUT)
    print(f"Đã ghi {os.path.basename(OUT)} (bản cũ: {os.path.basename(OUT)}.bak). Tool đang chạy sẽ tự nạp lại trong vòng 10 giây.")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
