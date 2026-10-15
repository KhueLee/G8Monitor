"""Cập nhật tên điểm (ô highbay) từ file Excel mapping -> nodes.json.
  python update_names.py "raw\\G8_mapping_Node_Highbay_20261007.xlsx"
  python update_names.py <file.xlsx> --check       -> chỉ kiểm tra, báo khác biệt, không ghi
Sheet đầu tiên, dòng 1 là tiêu đề; các cột cần có: Khu, Dãy, Node, Tên RCS (name), Tầng 1..Tầng 4.
Cần: pip install openpyxl. nodes.json cũ được sao lưu thành nodes.json.bak. Tool đang chạy tự nạp lại (không cần restart).
"""
import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # thư mục gốc project
CFG = json.load(open(os.path.join(ROOT, "config.json"), encoding="utf-8-sig"))
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
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = ws.iter_rows(values_only=True)
    head = [cell(h).lower() for h in next(rows)]

    def col(name):
        for i, h in enumerate(head):
            if h == name or h.startswith(name + " ") or h.startswith(name + "("):
                return i
        raise SystemExit(f"Sheet '{ws.title}' thiếu cột '{name}'. Các cột đang có: {head}")

    idx = {k: col(v) for k, v in COLS.items()}
    lv = [col(v) for v in LEVELS]
    nodes, skipped = [], 0
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
    return nodes, skipped


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
    if no_r:
        warn.append(f"{len(no_r)} dòng thiếu Tên RCS (vd. {', '.join(no_r[:5])})")
    try:
        pts = json.load(open(os.path.join(ROOT, CFG.get("map_dir", "data/map"), "points.json")))
        miss = [x["l"] for x in nodes if x["r"] not in pts and x["n"] not in pts]
        if miss:
            warn.append(f"{len(miss)} ô không có trên bản đồ hiện tại (vd. {', '.join(miss[:8])}) - kiểm tra mã Node/Tên RCS hoặc cập nhật bản đồ")
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
    nodes, skipped = read_xlsx(a.xlsx)
    if not nodes:
        raise SystemExit("Không đọc được dòng nào (cần cột Node và ít nhất Tầng 1).")
    print(f"Đọc {len(nodes)} điểm từ {os.path.basename(a.xlsx)}" + (f" (bỏ qua {skipped} dòng thiếu Node/Tầng 1)" if skipped else ""))
    print("Theo khu:", ", ".join(f"{k} {v}" for k, v in Counter(x["k"] for x in nodes).most_common()))
    for w in validate(nodes):
        print("  !", w)
    try:
        old = json.load(open(OUT, encoding="utf-8-sig"))
    except Exception:
        old = []
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
