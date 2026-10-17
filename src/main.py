"""G8 Monitor: nhận dữ liệu RCS/ICS đẩy lên (cảnh báo, trạng thái robot, trạng thái task), hỏi RCS định kỳ (đường đi robot,
danh sách task, bản đồ) nếu khai rcs_api, lưu log JSONL theo ngày, hiển thị trên web (tiếng Việt, dùng được trên điện thoại).
Chỉ cần: pip install starlette uvicorn
"""
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections import deque
from contextlib import asynccontextmanager

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

import cfg
import rcs_api

HERE = os.path.dirname(os.path.abspath(__file__))                    # src/
ROOT = cfg.ROOT                                                      # thư mục gốc project
CFG = cfg.load()                                                     # config.example.json + config.json của máy
LOG_DIR = CFG["log_dir"] if os.path.isabs(CFG["log_dir"]) else os.path.join(ROOT, CFG["log_dir"])
START = time.time()

ALARM_TYPES = {1: "Robot mất kết nối", 2: "Thiết bị hỏng", 3: "Pin yếu", 4: "AMR lỗi", 5: "Nâng cấp lỗi", 6: "Node lỗi", 8: "Lỗi dẫn đường",
               11: "Cập nhật bản đồ lỗi", 12: "Có vật cản", 15: "Nhiệt độ cao", 20: "Cọc sạc lỗi", 21: "Sạc lỗi", 22: "Kệ bất thường",
               23: "Đường đi bất thường", 24: "Lỗi cấu hình", 25: "Tải bất thường", 26: "Bin bất thường", 28: "Va chạm", 29: "Laser lỗi",
               30: "Hàng quá cao", 31: "Lỗi thay thiết bị", 40: "RFID lỗi", 41: "Cửa tự động lỗi", 42: "Thang máy lỗi", 43: "Cảm biến bin lỗi",
               44: "Camera lỗi", 45: "Chờ xác nhận", 46: "Dịch vụ lỗi", 48: "Pager lỗi", 49: "Đèn báo lỗi", 50: "Nhận diện lỗi"}
GRADE = {0: "Thấp", 1: "Vừa", 2: "Cao"}
ROBOT_STATUS = {0: "Mất kết nối", 1: "Rảnh", 2: "LỖI", 3: "Khởi động", 4: "Đang chạy task", 5: "Đang sạc", 7: "Đang nâng cấp"}
TASK_STATUS = {3: "Đã hủy", 5: "Gửi lỗi", 6: "Đang chạy", 7: "Chạy lỗi", 8: "Hoàn thành", 9: "Đã giao xe", 10: "Chờ xác nhận",
               20: "Đang lấy hàng", 21: "Đã lấy hàng", 22: "Đang trả hàng", 23: "Đã trả hàng"}

# ---------------------------------------------------------------- tra mã điểm (file highbay) + bản đồ + gợi ý lỗi
NODES_FILE = os.path.join(ROOT, CFG.get("nodes_file", "data/nodes.json"))
MAP_DIR = os.path.join(ROOT, CFG.get("map_dir", "data/map"))
BY_CODE, BY_LOC = {}, {}
HINTS = {"codes": {}, "types": {}}
POINTS, MAP = {}, None
CELLS = []                       # [(x_mm, y_mm, nhãn ô, khu)] toạ độ các ô highbay (lấy từ topo qua points.json)
LOADED = {}                      # file -> mtime lúc nạp, để tự nạp lại khi update_map.py / update_names.py ghi file mới
try:
    HINTS = json.load(open(os.path.join(ROOT, "data", "hints.json"), encoding="utf-8-sig"))
except Exception:
    pass


def mtime(p):
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0


def load_nodes():
    global BY_CODE, BY_LOC
    by_code, by_loc = {}, {}
    try:
        for n in json.load(open(NODES_FILE, encoding="utf-8-sig")):
            for k in (n["n"], n["r"]):
                if k:
                    by_code.setdefault(k, n)
            for t in n["t"]:
                by_loc[t.upper()] = n
    except Exception:
        return False
    BY_CODE, BY_LOC = by_code, by_loc
    LOADED["nodes"] = mtime(NODES_FILE)
    return True


def load_map():
    global POINTS, MAP
    try:
        pts = json.load(open(os.path.join(MAP_DIR, "points.json"), encoding="utf-8"))
        meta = json.load(open(os.path.join(MAP_DIR, "map_meta.json"), encoding="utf-8"))
    except Exception:
        return False
    POINTS, MAP = pts, meta
    LOADED["map"] = mtime(os.path.join(MAP_DIR, "map_meta.json"))
    return True


def build_cells():
    global CELLS
    cells = []
    for n in {id(v): v for v in BY_CODE.values()}.values():
        p = POINTS.get(n["r"]) or POINTS.get(n["n"])
        if p and n["l"]:
            cells.append((p[0], p[1], n["l"], n["k"]))
    CELLS = cells


def reload_if_changed():
    """Gọi định kỳ: file bản đồ hoặc tên điểm đổi thì nạp lại, không cần restart."""
    what = []
    if mtime(NODES_FILE) != LOADED.get("nodes") and load_nodes():
        what.append(f"tên điểm ({len(BY_CODE)} mã)")
    if mtime(os.path.join(MAP_DIR, "map_meta.json")) != LOADED.get("map") and load_map():
        what.append(f"bản đồ ({len(POINTS)} điểm)")
    if what:
        build_cells()
    return what


load_nodes()
load_map()
build_cells()


def to_pixel(xy_mm):
    """Toạ độ mm của RCS -> pixel trên ảnh bản đồ. Không có bản đồ/toạ độ thì trả None."""
    if not MAP or not xy_mm:
        return None
    ox, oy = CFG.get("xy_offset_mm", [0, 0])
    x = (float(xy_mm[0]) + ox) / 1000.0
    y = (float(xy_mm[1]) + oy) / 1000.0
    return [round((x - MAP["origin_x"]) / MAP["m_per_px"], 1), round(MAP["h"] - (y - MAP["origin_y"]) / MAP["m_per_px"], 1)]


def robot_xy(rec):
    """Ưu tiên toạ độ RCS gửi; không có thì lấy toạ độ của node (devicePosition)."""
    xy = rec.get("xy")
    if isinstance(xy, (list, tuple)) and len(xy) >= 2 and to_int(xy[0]) is not None and to_int(xy[1]) is not None:
        return [to_int(xy[0]), to_int(xy[1])]
    return POINTS.get(str(rec.get("pos") or ""))


def nearest_cell(xy):
    """Ô highbay gần nhất (dạng D36-16) với toạ độ mm. Trả về (nhãn, khu, khoảng cách m) hoặc None."""
    if not xy or not CELLS:
        return None
    best = min(CELLS, key=lambda c: (c[0] - xy[0]) ** 2 + (c[1] - xy[1]) ** 2)
    return best[2], best[3], ((best[0] - xy[0]) ** 2 + (best[1] - xy[1]) ** 2) ** 0.5 / 1000.0


def robot_place(rec):
    """Mô tả vị trí robot theo ô gần nhất mà người vận hành nhớ. Không có toạ độ thì dùng mã điểm."""
    n = nearest_cell(robot_xy(rec))
    if n:
        return f"Gần {n[0]} ({n[1]})" + (f", cách {n[2]:.0f} m" if n[2] >= 3 else "")
    return place(rec.get("pos")) or str(rec.get("pos") or "")


def place(code):
    code = str(code or "").strip()
    n = BY_CODE.get(code) or BY_LOC.get(code.upper())
    return f"{n['l']} ({n['k']})" if n else ""


# ---------------------------------------------------------------- log theo ngày
def day():
    return time.strftime("%Y-%m-%d")


def now_s(ts=None):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or time.time()))


def write_log(kind, rec):
    d = os.path.join(LOG_DIR, day())
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, kind + ".jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_lines(path, limit):
    """Đọc tối đa `limit` dòng cuối của file JSONL."""
    if not os.path.exists(path):
        return []
    out = deque(maxlen=limit)
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    out.append({"_bad": line[:200]})
    return list(out)


def cleanup_logs():
    keep = int(CFG.get("retention_days", 30))
    if not os.path.isdir(LOG_DIR):
        return
    limit = time.time() - keep * 86400
    for name in os.listdir(LOG_DIR):
        p = os.path.join(LOG_DIR, name)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", name) and os.path.isdir(p):
            try:
                if time.mktime(time.strptime(name, "%Y-%m-%d")) < limit:
                    shutil.rmtree(p, ignore_errors=True)
            except ValueError:
                pass


# ---------------------------------------------------------------- trạng thái trong bộ nhớ
ROBOTS = {}                      # key -> bản ghi mới nhất
ALARMS = {}                      # key -> {first,last,count,...}
TASK_EVENTS = deque(maxlen=400)
TASKS = {}                       # orderId -> sự kiện mới nhất
INCIDENTS = deque(maxlen=600)
CHAN = {k: {"last": 0, "count": 0, "today": 0, "day": day()} for k in ("alarm", "agv", "task")}
FLAGS = {"silent": False}


def clean(obj):
    """Bỏ khoảng trắng thừa ở tên trường và giá trị (RCS thật hay gửi "deviceName " ...)."""
    if isinstance(obj, dict):
        return {str(k).strip(): clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj.strip() if isinstance(obj, str) else obj


def to_int(v, default=None):
    try:
        return int(float(str(v).strip()))
    except (TypeError, ValueError):
        return default


def incident(kind, level, title, detail="", device="", ts=None, persist=True):
    rec = {"ts": ts or time.time(), "time": now_s(ts), "kind": kind, "level": level, "title": title, "detail": detail, "device": device}
    INCIDENTS.append(rec)
    if persist:
        write_log("incident", rec)


def mark(ch):
    c = CHAN[ch]
    if c["day"] != day():
        c["day"], c["today"] = day(), 0
    c["last"], c["count"], c["today"] = time.time(), c["count"] + 1, c["today"] + 1
    if ch == "agv" and FLAGS["silent"]:
        FLAGS["silent"] = False
        incident("system", "low", "RCS gửi dữ liệu robot trở lại")


def robot_name(d):
    raw = str(d.get("deviceName") or d.get("deviceNum") or d.get("deviceCode") or "?")
    return CFG.get("alias", {}).get(raw) or CFG.get("alias", {}).get(str(d.get("deviceCode") or "")) or raw


def handle_agv(items):
    mark("agv")
    now = time.time()
    for d in items:
        if not isinstance(d, dict):
            continue
        name = robot_name(d)
        status = to_int(d.get("deviceStatus"))
        state = str(d.get("state") or "")
        batt = to_int(d.get("battery"))
        pos = str(d.get("devicePosition") or "")
        xy = d.get("devicePostionRec") or d.get("devicePositionRec") or []
        rec = {"name": name, "code": str(d.get("deviceCode") or ""), "status": status, "state": state, "battery": batt, "pos": pos,
               "xy": xy, "order": str(d.get("orderId") or ""), "shelf": str(d.get("shelfNumber") or d.get("shelfNum") or ""),
               "path": str(d.get("taskPath") or ""), "speed": to_int(d.get("speed")), "payload": str(d.get("payLoad") or ""), "ts": now}
        prev = ROBOTS.get(name)
        cur = robot_xy(rec)
        rec["moved_ts"] = now
        if prev is not None:
            pcur = robot_xy(prev)
            if cur and pcur and ((cur[0] - pcur[0]) ** 2 + (cur[1] - pcur[1]) ** 2) ** 0.5 < float(CFG.get("stuck_move_mm", 500)):
                rec["moved_ts"] = prev.get("moved_ts", now)
            rec["chg_ts"], rec["chg_batt"] = prev.get("chg_ts"), prev.get("chg_batt")
            rec["stuck_flag"] = prev.get("stuck_flag") and rec["moved_ts"] != now
        if status == 5:                                   # theo dõi pin khi sạc
            if rec.get("chg_ts") is None or (batt is not None and rec.get("chg_batt") is not None and batt > rec["chg_batt"] + 1):
                rec["chg_ts"], rec["chg_batt"] = now, batt
        else:
            rec["chg_ts"] = rec["chg_batt"] = None
        if prev is None:
            if status == 2:
                incident("robot", "high", f"{name} đang ở trạng thái LỖI", f"Vị trí: {robot_place(rec)}", name)
        else:
            if prev.get("lost"):
                incident("robot", "low", f"{name} có tín hiệu trở lại", "", name)
            ps = prev.get("status")
            if status != ps:
                if status == 2:
                    incident("robot", "high", f"{name} báo LỖI", f"Vị trí: {robot_place(rec)}", name)
                elif ps == 2:
                    incident("robot", "low", f"{name} hết lỗi", f"Trạng thái: {ROBOT_STATUS.get(status, status)}", name)
                if status == 0:
                    incident("robot", "mid", f"{name} mất kết nối (offline)", "", name)
                elif ps == 0:
                    incident("robot", "low", f"{name} online trở lại", "", name)
            low = int(CFG.get("battery_low", 20))
            if batt is not None and batt < low and (prev.get("battery") is None or prev["battery"] >= low) and status != 5:
                incident("robot", "mid", f"{name} pin thấp ({batt}%)", "", name)
        # ghi log: khi đổi trạng thái/task/kệ/pin, hoặc theo chu kỳ
        last = (prev or {}).get("_logged", 0)
        changed = prev is None or any(prev.get(k) != rec[k] for k in ("status", "order", "shelf")) or \
            (batt is not None and prev.get("battery") is not None and abs(batt - prev["battery"]) >= 5)
        if changed or now - last >= float(CFG.get("agv_log_interval_sec", 30)):
            write_log("agv", {"time": now_s(), "name": name, "code": rec["code"], "status": status, "state": state, "battery": batt,
                              "pos": pos, "xy": xy, "order": rec["order"], "shelf": rec["shelf"], "speed": rec["speed"]})
            rec["_logged"] = now
        else:
            rec["_logged"] = last
        ROBOTS[name] = rec


REASON_VI = {"LableNotFound": "Không thấy nhãn/mã kệ (LableNotFound)", "FreePathObstacleInPath": "Có vật cản trên đường đi (FreePathObstacleInPath)"}
DIR_VI = {"front": "phía trước", "back": "phía sau", "left": "bên trái", "right": "bên phải"}


def parse_alarm_desc(desc):
    """RCS gửi alarmDesc dạng JSON. Trả về (mô tả dễ đọc, mã lỗi số, id sự kiện, toạ độ mm)."""
    try:
        j = json.loads(desc)
    except Exception:
        return desc, "", "", None
    if not isinstance(j, dict):
        return desc, "", "", None
    pos = j.get("Position")
    if isinstance(pos, str):
        try:
            pos = json.loads(pos)
        except Exception:
            pos = None
    parts = []
    rd = str(j.get("ReasonDesc") or j.get("Reason") or "")
    if rd and not rd.isdigit():
        parts.append(REASON_VI.get(rd, rd))
    if j.get("Direction"):
        parts.append("hướng " + DIR_VI.get(j["Direction"], str(j["Direction"])))
    if j.get("TargetShelfNo"):
        parts.append(f"kệ cần lấy {j['TargetShelfNo']}")
    if j.get("TaskID"):
        parts.append(f"task {j['TaskID']}")
    code = ""
    r = j.get("Reason")
    if isinstance(r, int) and r >= 1000:
        code = str(r)
    return ("; ".join(parts) or desc), code, str(j.get("Id") or ""), (pos if isinstance(pos, list) and len(pos) == 2 else None)


def handle_alarm(d):
    mark("alarm")
    now = time.time()
    atype = to_int(d.get("alarmType"), 0)
    raw_desc = str(d.get("alarmDesc") or "")
    desc, jcode, eid, apos = parse_alarm_desc(raw_desc)
    dev = str(d.get("deviceNum") or d.get("deviceName") or "")
    dev = CFG.get("alias", {}).get(dev, dev)
    src = str(d.get("channelDeviceId") or "")
    resolved = to_int(d.get("alarmStatus")) == 1
    m = re.search(r"\((\d{4,5})\)", raw_desc)
    code = m.group(1) if m else jcode
    key = f"{dev}|{atype}|{eid or src}|{raw_desc[:80]}"
    rec = ALARMS.get(key)
    near = nearest_cell(apos) if apos else None
    where = f"gần {near[0]} ({near[1]})" if near else ""
    if rec and now - rec["last"] <= float(CFG.get("alarm_dedup_sec", 300)):
        was = rec["resolved"]
        rec["last"], rec["count"] = now, rec["count"] + 1
        rec["resolved"] = resolved
        if resolved and not was:
            incident("alarm", "low", f"{rec['device']}: {rec['type_name']} đã hết", desc, rec["device"])
    else:
        rec = {"key": key, "first": now, "last": now, "count": 1, "device": dev, "type": atype, "type_name": ALARM_TYPES.get(atype, f"Loại {atype}"),
               "desc": desc, "grade": to_int(d.get("alarmGrade"), 0), "grade_name": GRADE.get(to_int(d.get("alarmGrade"), 0), "?"),
               "source": src, "place": where or place(src), "hint": str(d.get("channelName") or "").replace("\\r\\n", " ").replace("\r\n", " "),
               "err_code": code, "resolved": resolved, "area": d.get("areaId")}
        ALARMS[key] = rec
        if not resolved:                      # cảnh báo đến lần đầu đã ở trạng thái hết thì không tạo sự cố mới
            lvl = {2: "high", 1: "mid"}.get(rec["grade"], "low")
            incident("alarm", lvl, f"{rec['device'] or 'Hệ thống'}: {rec['type_name']}" + (f" (mã {rec['err_code']})" if rec["err_code"] else ""),
                     (desc + (f" · Tại {where or src}" if (where or src) else "")).strip(), rec["device"])
    write_log("alarm", {"time": now_s(), **{k: rec[k] for k in ("device", "type", "type_name", "desc", "grade", "source", "err_code", "resolved", "hint")},
                        "alarmDate_raw": d.get("alarmDate"), "count": rec["count"], "pos": apos, "raw": raw_desc})


def handle_task(d):
    mark("task")
    status = to_int(d.get("status"))
    ev = {"ts": time.time(), "time": now_s(), "order": str(d.get("orderId") or ""), "status": status, "status_name": TASK_STATUS.get(status, str(status)),
          "device": CFG.get("alias", {}).get(str(d.get("deviceNum") or ""), str(d.get("deviceNum") or "")), "point": str(d.get("qrContent") or ""),
          "point_place": place(d.get("qrContent")), "template": str(d.get("modelProcessCode") or ""), "error": str(d.get("errorDesc") or ""),
          "shelf": str(d.get("shelfNumber") or ""), "sub_status": str(d.get("subTaskStatus") or ""), "sub_type": str(d.get("subTaskTypeId") or "")}
    TASK_EVENTS.append(ev)
    TASKS[ev["order"]] = ev
    if len(TASKS) > 800:
        for k in list(TASKS)[:200]:
            TASKS.pop(k, None)
    write_log("task", ev)
    if status in (5, 7):
        incident("task", "high", f"Task {ev['status_name'].lower()}: {ev['order'] or '(không mã)'}",
                 f"{ev['error']} · Robot {ev['device'] or '?'} · Điểm {ev['point']} {ev['point_place']}".strip(" ·"), ev["device"])


# ---------------------------------------------------------------- hỏi RCS định kỳ (getRobotTaskPath, getOrderList); topologyList chỉ gọi khi bấm nút tải map
API = CFG.get("rcs_api") or {}
API_ON = bool(API.get("base")) and API.get("enabled", True) is not False
AUTH = {"need": False, "ts": 0, "err": ""}   # RCS đòi user/password -> giao diện hiện cửa sổ nhập
API_NAMES = {"path": "getRobotTaskPath (đường đi robot)", "order": "getOrderList (danh sách task)"}
API_EVERY = {"path": float(API.get("path_sec", 5)), "order": float(API.get("order_sec", 30))}
API_ST = {k: {"ok": 0, "try": 0, "count": 0, "err": "", "fail": False} for k in API_NAMES}
ORDER_STATUS = {1: "Chưa gửi", 2: "Đang hủy", 3: "Đã hủy", 4: "Đang gửi", 5: "Gửi lỗi", 6: "Đang chạy", 7: "Chạy lỗi", 8: "Hoàn thành", 9: "Đã giao xe"}
ROUTES = {}                      # tên robot -> {"nodes": [[mã, x, y], ...], "ts", "area"}
ORDERS = {"list": [], "ts": 0, "total": None}
ORDER_SEEN = {}                  # orderId -> trạng thái đã ghi log (chỉ ghi khi đổi)


def parse_path_node(v):
    """pathNodes: "mã QR,x,y,góc" (mm). Trả về [mã, x, y] hoặc None."""
    parts = v if isinstance(v, (list, tuple)) else str(v).split(",")
    if len(parts) < 3 or to_int(parts[1]) is None or to_int(parts[2]) is None:
        return None
    return [str(parts[0]).strip(), to_int(parts[1]), to_int(parts[2])]


def on_paths(data):
    now, seen = time.time(), set()
    for area in (data or {}).get("areaInfo") or []:
        for dev in area.get("devices") or []:
            raw = str(dev.get("deviceNum") or dev.get("deviceCode") or "")
            name = CFG.get("alias", {}).get(raw) or CFG.get("alias", {}).get(str(dev.get("deviceCode") or "")) or raw
            nodes = [p for p in (parse_path_node(v) for v in dev.get("pathNodes") or []) if p]
            seen.add(name)
            prev = (ROUTES.get(name) or {}).get("nodes") or []
            codes, pcodes = [n[0] for n in nodes], [n[0] for n in prev]
            # robot đi tới đâu RCS bỏ bớt điểm đầu -> chỉ ghi log khi có đường mới (đích khác / đổi tuyến), không ghi mỗi lần rút ngắn
            if codes and (not pcodes or codes != pcodes[len(pcodes) - len(codes):]):
                write_log("path", {"time": now_s(now), "name": name, "code": str(dev.get("deviceCode") or ""), "area": area.get("areaId"),
                                   "from": codes[0], "to": codes[-1], "to_place": place(codes[-1]), "count": len(codes), "nodes": dev.get("pathNodes"),
                                   "lock_rects": len(dev.get("pathLockRects") or []), "reroute": bool(pcodes) and pcodes[-1] == codes[-1]})
            ROUTES[name] = {"nodes": nodes, "ts": now, "area": area.get("areaId")}
    for name in list(ROUTES):
        if name not in seen:
            ROUTES.pop(name)


def on_orders(data):
    data = data or {}
    tasks = data.get("Tasks") or []
    ORDERS.update(ts=time.time(), total=data.get("totalCount"), list=[{
        "order": str(t.get("OrderId") or ""), "task_id": t.get("TaskId"), "number": str(t.get("OrderNumber") or ""), "status": to_int(t.get("OrderStatus")),
        "status_name": ORDER_STATUS.get(to_int(t.get("OrderStatus")), str(t.get("OrderStatus"))), "template": str(t.get("TemplateCode") or ""),
        "template_name": str(t.get("TemplateName") or ""), "path": str(t.get("OrderPath") or ""), "priority": to_int(t.get("Priority")),
        "robot_type": str(t.get("RobotType") or ""), "created": str(t.get("createTime") or ""), "zone": t.get("ZoneId")} for t in tasks if isinstance(t, dict)])
    for o in ORDERS["list"]:
        if ORDER_SEEN.get(o["order"]) == o["status"]:
            continue
        first = o["order"] not in ORDER_SEEN
        ORDER_SEEN[o["order"]] = o["status"]
        write_log("order", {"time": now_s(), **o})
        cb = TASKS.get(o["order"])                         # callback task-status đã báo lỗi này thì không báo trùng
        if o["status"] in (5, 7) and not first and not (cb and cb.get("status") == o["status"]):
            incident("task", "high", f"Task {o['status_name'].lower()}: {o['order']}", f"{o['template_name'] or o['template']} · đường {o['path']} (theo getOrderList)")
    if len(ORDER_SEEN) > 5000:
        for k in list(ORDER_SEEN)[:2000]:
            ORDER_SEEN.pop(k, None)


def rcs_fetch(kind, body):
    """Chạy trong luồng phụ (gọi mạng). Mọi lần gọi (kể cả lỗi) ghi nguyên phản hồi RCS vào api.jsonl nếu bật log_api."""
    trace = {}
    try:
        return rcs_api.call(API, kind, body, trace)
    except Exception as e:
        trace["error"] = str(e)[:500]
        raise
    finally:
        if CFG.get("log_api", True):
            write_log("api", {"time": now_s(), "api": kind, **trace})


async def rcs_poller():
    handlers = {"path": on_paths, "order": on_orders}
    bodies = {"path": {"areaId": int(API.get("area_id", 1))},
              "order": {"areaId": int(API.get("area_id", 1)), "StartPage": "1", "pageSize": str(API.get("order_page_size", 50))}}
    while True:
        for kind, st in API_ST.items():
            if API_EVERY[kind] <= 0 or time.time() - st["try"] < API_EVERY[kind]:
                continue
            st["try"] = time.time()
            try:
                data = await asyncio.to_thread(rcs_fetch, kind, bodies[kind])
                handlers[kind](data)
                st.update(ok=time.time(), count=st["count"] + 1, err="")
                AUTH["need"] = False
                if st["fail"]:
                    st["fail"] = False
                    incident("system", "low", f"Gọi được API RCS {API_NAMES[kind]} trở lại")
            except Exception as e:
                st["err"] = str(e)[:300]
                if isinstance(e, rcs_api.RcsAuthError):
                    AUTH.update(need=True, ts=time.time(), err=st["err"])
                if not st["fail"]:
                    st["fail"] = True
                    incident("system", "mid", f"Không gọi được API RCS {API_NAMES[kind]}", st["err"])
        await asyncio.sleep(1)


def is_jump(a, b):
    """Hai điểm liền nhau cách xa và nằm chéo (không chạy dọc lối đi) -> không vẽ đoạn nối thẳng (tránh đường chéo cắt ngang bản đồ)."""
    dx, dy = abs(b[0] - a[0]), abs(b[1] - a[1])
    d = (dx * dx + dy * dy) ** 0.5
    return d > float(CFG.get("route_jump_mm", 3000)) and min(dx, dy) > 0.17 * d       # lệch trục > ~10 độ


def route_view(name, xy=None):
    """Đường đi còn lại của robot: bỏ các điểm đã đi qua (trước điểm gần robot nhất), cắt thành nhiều đoạn ở chỗ nhảy chéo."""
    r = ROUTES.get(name)
    if not r or not r["nodes"]:
        return None
    nodes = r["nodes"]
    if xy:
        i = min(range(len(nodes)), key=lambda k: (nodes[k][1] - xy[0]) ** 2 + (nodes[k][2] - xy[1]) ** 2)
        nodes = nodes[i:]
    segs, cur, prev = [], [], None
    if xy and not is_jump(xy, nodes[0][1:]):                     # nối từ robot tới điểm kế tiếp nếu gần
        cur, prev = [to_pixel(xy)], xy
    for n in nodes:
        if prev is not None and is_jump(prev, n[1:]):
            segs.append(cur)
            cur = []
        cur.append(to_pixel(n[1:]))
        prev = n[1:]
    segs.append(cur)
    segs = [[p for p in sg if p] for sg in segs]
    to = nodes[-1][0]
    return {"count": len(nodes), "to": to, "to_place": place(to), "segs": [sg for sg in segs if len(sg) > 1], "end": to_pixel(nodes[-1][1:])}


# ---------------------------------------------------------------- nhận callback từ RCS
OK = {"code": 1000, "desc": "success"}


async def receive(request, kind):
    body = await request.body()
    ip = request.client.host if request.client else ""
    data = None
    for enc in ("utf-8-sig", "gbk", "latin-1"):
        try:
            data = json.loads(body.decode(enc))
            break
        except (ValueError, UnicodeDecodeError):
            continue
    if CFG.get("log_push", True) and data is not None:     # lưu nguyên bản tin RCS đẩy lên
        write_log("push", {"time": now_s(), "kind": kind, "ip": ip, "body": data})
    if data is None:
        write_log("raw", {"time": now_s(), "kind": kind, "ip": ip, "ok_json": False, "body": body[:4000].decode("utf-8", "replace")})
    if data is None:
        incident("system", "mid", f"RCS gửi dữ liệu {kind} không đọc được (không phải JSON)", f"từ {ip}")
        return JSONResponse(OK)          # vẫn trả 1000 để RCS không gửi lại liên tục
    data = clean(data)
    try:
        if kind == "agv":
            handle_agv(data if isinstance(data, list) else [data])
        elif kind == "alarm":
            for d in (data if isinstance(data, list) else [data]):
                handle_alarm(d)
        else:
            for d in (data if isinstance(data, list) else [data]):
                handle_task(d)
    except Exception as e:       # lỗi xử lý không được làm RCS gửi lại
        write_log("raw", {"time": now_s(), "kind": kind, "error": f"{type(e).__name__}: {e}", "body": str(data)[:2000]})
    return JSONResponse(OK)


# ---------------------------------------------------------------- API cho giao diện
def J(d, status=200):
    return JSONResponse(d, status_code=status, headers={"Cache-Control": "no-store"})


def dur_vi(sec):
    sec = int(sec)
    return f"{sec} giây" if sec < 60 else f"{sec // 60} phút" if sec < 3600 else f"{sec // 3600} giờ {sec % 3600 // 60} phút"


def predict(r, now):
    """Lỗi dự đoán cho một robot, suy ra từ cảnh báo RCS, trạng thái, vị trí đứng yên, pin, task lỗi."""
    name, out = r["name"], []

    def add(level, title, detail=""):
        out.append({"level": level, "title": title, "detail": detail})

    act = float(CFG.get("alarm_active_minutes", 10)) * 60
    for a in sorted(ALARMS.values(), key=lambda a: -a["last"]):
        if a["device"] == name and not a["resolved"] and now - a["last"] <= act:
            code = a["err_code"]
            h = HINTS["codes"].get(code)
            title = a["type_name"] + (f" (mã {code})" if code else "")
            detail = f"{h[0]}. Cách xử lý: {h[1]}" if h else (HINTS["types"].get(str(a["type"])) or a["desc"])
            if a["source"]:
                detail += f" Tại điểm {a['source']}" + (f" ({a['place']})" if a["place"] else "") + "."
            if a["hint"] and not h:
                detail += " Gợi ý RCS: " + a["hint"]
            add({2: "high", 1: "mid"}.get(a["grade"], "low"), title, detail)
    if r.get("unseen"):
        return out
    st = r["status"]
    if r.get("lost"):
        add("high", f"Mất tín hiệu {dur_vi(r['age'])}", "Có thể do Wi-Fi, tắt máy hoặc hết pin. Kiểm tra tại xe. Vị trí cuối: " + (r["place"] or "không rõ") + ".")
    elif st == 0 or str(r.get("state")) == "Offline":
        add("mid", "Robot offline", "Kiểm tra mạng, khởi động lại thiết bị. Ngoài ca có thể do tắt máy.")
    if st == 2 and not any(p["level"] == "high" for p in out):
        add("high", "Robot báo LỖI (Fault)", "RCS chưa gửi chi tiết. Xem cảnh báo của robot trên RCS hoặc ra kiểm tra tại xe.")
    b = r.get("battery")
    if b is not None and b < int(CFG.get("battery_low", 20)) and st != 5:
        add("mid", f"Pin thấp ({b}%)", "Đưa robot đi sạc.")
    if st == 4 and not r.get("lost") and now - r.get("moved_ts", now) >= float(CFG.get("stuck_sec", 180)):
        add("mid", f"Nghi kẹt: đứng yên {dur_vi(now - r['moved_ts'])} khi đang chạy task",
            "Thường do robot khác/kệ/vật cản chắn đường hoặc chờ điều phối. Xem tab Sự cố có cảnh báo vật cản/chặn đường không.")
    if st == 5 and r.get("chg_ts") and now - r["chg_ts"] >= float(CFG.get("charge_stall_min", 30)) * 60:
        add("mid", f"Đang sạc {dur_vi(now - r['chg_ts'])} nhưng pin không tăng", "Kiểm tra tiếp điểm sạc và trạm sạc.")
    for ev in reversed(TASK_EVENTS):
        if ev["device"] == name and ev["status"] in (5, 7) and now - ev["ts"] <= float(CFG.get("task_fail_minutes", 30)) * 60:
            add("mid", f"Task vừa {ev['status_name'].lower()}", (ev["error"] or "RCS không nêu lý do") + f" · task {ev['order']}")
            break
    out.sort(key=lambda p: {"high": 0, "mid": 1, "low": 2}[p["level"]])
    return out


def robots_view():
    now = time.time()
    out = []
    for r in ROBOTS.values():
        age = now - r["ts"]
        lost = age > float(CFG.get("robot_stale_sec", 60))
        d = {**{k: v for k, v in r.items() if not k.startswith("_")}, "age": int(age), "lost": lost,
             "status_name": ROBOT_STATUS.get(r["status"], r["state"] or "?"), "place": robot_place(r), "path_text": r["path"]}
        d["map"] = to_pixel(robot_xy(r))
        d["route"] = route_view(r["name"], robot_xy(r))
        d["preds"] = predict(d, now)
        out.append(d)
    for name in CFG.get("robots", []):          # robot khai trong config nhưng chưa có dữ liệu
        if name not in ROBOTS:
            out.append({"name": name, "status": None, "state": "", "battery": None, "pos": "", "xy": [], "order": "", "shelf": "", "path": "", "speed": None,
                        "payload": "", "code": "", "age": None, "lost": False, "unseen": True, "status_name": "Chưa có dữ liệu", "place": "", "path_text": "",
                        "map": None, "route": route_view(name), "preds": []})
    order = {n: i for i, n in enumerate(CFG.get("robots", []))}
    out.sort(key=lambda x: (0 if x["status"] == 2 else 1 if (x["lost"] or x["status"] == 0) else 3 if x.get("unseen") else 2, order.get(x["name"], 99), x["name"]))
    return out


async def api_state(request: Request):
    now = time.time()
    rob = robots_view()
    act = [a for a in ALARMS.values() if not a["resolved"] and now - a["last"] <= float(CFG.get("alarm_active_minutes", 10)) * 60]
    silence = now - CHAN["agv"]["last"] if CHAN["agv"]["last"] else None
    return J({"now": now_s(), "robots": rob,
              "summary": {"total": len(rob), "unseen": sum(1 for r in rob if r.get("unseen")), "fault": sum(1 for r in rob if r["status"] == 2), "lost": sum(1 for r in rob if r["lost"] or r["status"] == 0),
                          "running": sum(1 for r in rob if r["status"] == 4 and not r["lost"]), "idle": sum(1 for r in rob if r["status"] == 1 and not r["lost"]),
                          "charging": sum(1 for r in rob if r["status"] == 5 and not r["lost"]), "active_alarms": len(act)},
              "silence_sec": int(silence) if silence is not None else None, "silence_warn": float(CFG.get("silence_warn_sec", 120)),
              "never": CHAN["agv"]["last"] == 0, "auth": {**AUTH, "user": API.get("user", "")} if API_ON else None})


# ---------------------------------------------------------------- nút cập nhật map / highbay (chạy tools\update_map.py, update_names.py)
UPLOAD_DIR = os.path.join(ROOT, "raw", "upload")    # file map/highbay tải lên hoặc tải từ RCS (không đưa lên git)
JOB = asyncio.Lock()                                # mỗi lúc chỉ chạy một việc cập nhật


def run_tool(script, *args):
    """Chạy công cụ trong thư mục tools bằng tiến trình con, trả về (mã thoát, nội dung in ra)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, os.path.join(ROOT, "tools", script), *args], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
    return p.returncode, (p.stdout + "\n" + p.stderr).strip()


KEEP_UPLOADS = 5                                    # giữ 5 file gần nhất mỗi loại trong raw\upload


def upload_path(prefix, ext):
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    olds = sorted(f for f in os.listdir(UPLOAD_DIR) if f.startswith(prefix + "_") and f.endswith(ext))
    for f in olds[:max(0, len(olds) - KEEP_UPLOADS + 1)]:
        try:
            os.remove(os.path.join(UPLOAD_DIR, f))
        except OSError:
            pass
    return os.path.join(UPLOAD_DIR, f"{prefix}_{time.strftime('%Y%m%d-%H%M%S')}{ext}")


def save_upload(prefix, ext, blob):
    path = upload_path(prefix, ext)
    with open(path, "wb") as f:
        f.write(blob)
    return path


# Tải map từ RCS về MÁY CHỦ trước (mạng LAN ổn định), máy xem web kéo file từ máy chủ sau (theo khúc, mất gói thì thử lại khúc đó).
# MAPJOB: tiến độ để giao diện hỏi định kỳ. stage: fetch (hỏi topologyList) -> download -> build (chỉ khi cập nhật) -> done | error
MAPJOB = {"state": "idle", "mode": "", "stage": "", "bytes": 0, "total": 0, "file": "", "size": 0, "error": "", "log": "", "auth": False, "ts": 0}


def rcs_map_to_host():
    """Chạy trong luồng phụ: gọi topologyList, tải file mapZipUrl về raw/upload. Trả về đường dẫn file."""
    data = rcs_fetch("topology", {"areaId": int(API.get("area_id", 1))}) or {}
    url = data.get("mapZipUrl") or ""
    if not url:
        raise rcs_api.RcsError(f"RCS không trả link map zip (trả về: {json.dumps(data, ensure_ascii=False)[:300]})")
    MAPJOB["stage"] = "download"
    path = upload_path(f"rcs_map_area{API.get('area_id')}", ".zip")
    trace = {"url": url.split("?")[0]}
    t0 = time.time()
    try:
        n = rcs_api.download_to(url, path + ".part", lambda got, total: MAPJOB.update(bytes=got, total=total))
        with open(path + ".part", "rb") as f:
            head = f.read(200)
        if not head.startswith(b"PK"):
            raise rcs_api.RcsError(f"RCS trả về file không phải zip ({n} byte): {head[:120].decode('utf-8', 'replace')}")
        os.replace(path + ".part", path)
        trace.update(bytes=n, sec=round(time.time() - t0, 1), saved=os.path.relpath(path, ROOT))
        return path
    except Exception as e:
        trace["error"] = str(e)[:500]
        try:
            os.remove(path + ".part")
        except OSError:
            pass
        raise
    finally:
        if CFG.get("log_api", True):
            write_log("api", {"time": now_s(), "api": "map_download", "map_id": data.get("mapId"), **trace})


async def map_job(mode):
    async with JOB:
        try:
            path = await asyncio.to_thread(rcs_map_to_host)
            MAPJOB.update(file=os.path.basename(path), size=os.path.getsize(path))
            if mode == "update":
                MAPJOB["stage"] = "build"
                code, out = await asyncio.to_thread(run_tool, "update_map.py", path)
                MAPJOB["log"] = out
                if code != 0:
                    raise RuntimeError("dựng bản đồ không thành công, xem chi tiết bên dưới")
                reload_now()
                incident("system", "low", "Đã cập nhật bản đồ từ RCS", f"{MAPJOB['file']} · {MAPJOB['size'] // 1024} KB")
            else:
                incident("system", "low", "Đã tải map RCS về máy chủ", f"{MAPJOB['file']} · {MAPJOB['size'] // 1024} KB")
            MAPJOB.update(state="done", stage="done")
        except Exception as e:
            if isinstance(e, rcs_api.RcsAuthError):
                AUTH.update(need=True, ts=time.time(), err=str(e)[:300])
            MAPJOB.update(state="error", error=str(e)[:500], auth=isinstance(e, rcs_api.RcsAuthError))
            incident("system", "mid", "Cập nhật bản đồ từ RCS lỗi" if mode == "update" else "Tải map từ RCS lỗi", MAPJOB["error"])


async def api_map_job(request: Request):
    """Bắt đầu tải map từ RCS về máy chủ (mode=save) hoặc tải rồi cập nhật bản đồ (mode=update). Tiến độ: GET /api/map-job."""
    if request.method == "GET":
        return J({**MAPJOB, "age": int(time.time() - MAPJOB["ts"]) if MAPJOB["ts"] else None})
    mode = "update" if request.query_params.get("mode") == "update" else "save"
    if not API_ON:
        return J({"error": "đang tắt rcs_api trong config.json"}, 400)
    if JOB.locked() or MAPJOB["state"] == "run":
        return J({"error": "đang có một cập nhật khác chạy, chờ xong rồi bấm lại"}, 409)
    MAPJOB.update(state="run", mode=mode, stage="fetch", bytes=0, total=0, file="", size=0, error="", log="", auth=False, ts=time.time())
    asyncio.create_task(map_job(mode))
    return J({"ok": True})


async def api_map_file(request: Request):
    """Máy xem web kéo file map từ máy chủ. Hỗ trợ header Range để tải theo khúc và tải lại khúc lỗi."""
    name = request.query_params.get("name") or ""
    path = os.path.join(UPLOAD_DIR, name)
    if not re.fullmatch(r"rcs_map_area\w*_\d{8}-\d{6}\.zip", name) or not os.path.exists(path):
        return J({"error": "không thấy file map trên máy chủ, bấm tải lại"}, 404)
    size = os.path.getsize(path)
    m = re.fullmatch(r"bytes=(\d+)-(\d*)", (request.headers.get("range") or "").strip())
    if not m:
        return FileResponse(path, filename=name, headers={"Accept-Ranges": "bytes", "Cache-Control": "no-store"})
    a = int(m.group(1))
    b = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
    if a > b:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
    with open(path, "rb") as f:
        f.seek(a)
        data = f.read(b - a + 1)
    return Response(data, status_code=206, media_type="application/zip",
                    headers={"Content-Range": f"bytes {a}-{b}/{size}", "Accept-Ranges": "bytes", "Cache-Control": "no-store"})


def reload_now():
    what = reload_if_changed()
    if what:
        incident("system", "low", "Đã nạp lại " + " và ".join(what), (f"Bản đồ: {MAP.get('source')}" if MAP and MAP.get("source") and "bản đồ" in what[-1] else ""))


async def api_map_update(request: Request):
    """Nút "Cập nhật từ file zip": file zip người dùng tải lên -> tách ảnh nền + topology, thay toàn bộ bản đồ đang hiển thị."""
    if JOB.locked() or MAPJOB["state"] == "run":
        return J({"error": "đang có một cập nhật khác chạy, chờ xong rồi bấm lại"}, 409)
    async with JOB:
        blob = await request.body()
        if not blob.startswith(b"PK"):
            return J({"error": "file tải lên không phải file zip"}, 400)
        path = save_upload("map", ".zip", blob)
        try:
            code, out = await asyncio.to_thread(run_tool, "update_map.py", path)
        except Exception as e:
            code, out = -1, f"{type(e).__name__}: {e}"
        rel = os.path.relpath(path, ROOT)
        if code == 0:
            reload_now()
            incident("system", "low", "Đã cập nhật bản đồ", f"từ {rel}")
        else:
            incident("system", "mid", "Cập nhật bản đồ lỗi", out.splitlines()[-1] if out else rel)
        return J({"ok": code == 0, "log": out, "file": rel, "error": "" if code == 0 else "cập nhật bản đồ không thành công, xem chi tiết bên dưới"})


async def api_highbay(request: Request):
    """Nút "Cập nhật highbay": body = file Excel mapping .xlsx -> bóc tách, ghi nodes.json, nạp lại ngay."""
    if JOB.locked() or MAPJOB["state"] == "run":
        return J({"error": "đang có một cập nhật khác chạy, chờ xong rồi bấm lại"}, 409)
    async with JOB:
        blob = await request.body()
        if not blob.startswith(b"PK"):
            return J({"error": "file tải lên không phải file Excel .xlsx"}, 400)
        path = save_upload("highbay", ".xlsx", blob)
        code, out = await asyncio.to_thread(run_tool, "update_names.py", path)
        rel = os.path.relpath(path, ROOT)
        if code == 0:
            reload_now()
            incident("system", "low", "Đã cập nhật bảng highbay", f"từ {rel}")
        return J({"ok": code == 0, "log": out, "file": rel, "error": "" if code == 0 else "không đọc được file, xem chi tiết bên dưới"})


async def api_rcs_auth(request: Request):
    """Lưu user/password RCS (cửa sổ nhập trên giao diện) vào config.json rồi hỏi lại RCS ngay."""
    try:
        d = await request.json()
    except ValueError:
        return J({"error": "dữ liệu không hợp lệ"}, 400)
    user, pw = str(d.get("user") or "").strip(), str(d.get("password") or "")
    cfg.save_rcs_auth(user, pw)
    API.update(user=user, password=pw)
    AUTH.update(need=False, err="")
    for st in API_ST.values():
        st["try"] = 0
    incident("system", "low", "Đã lưu user/password RCS" if user else "Đã xoá user/password RCS", f"user: {user}" if user else "")
    return J({"ok": True})


async def api_incidents(request: Request):
    now = time.time()
    hours = float(request.query_params.get("hours") or 24)
    inc = [i for i in INCIDENTS if now - i["ts"] <= hours * 3600]
    inc.reverse()
    act = [a for a in ALARMS.values() if not a["resolved"] and now - a["last"] <= float(CFG.get("alarm_active_minutes", 10)) * 60]
    act.sort(key=lambda a: (-a["grade"], -a["last"]))
    fmt = lambda a: {**{k: v for k, v in a.items() if k != "key"}, "first_s": now_s(a["first"]), "last_s": now_s(a["last"]), "ago": int(now - a["last"])}
    return J({"incidents": inc[:300], "active": [fmt(a) for a in act]})


async def api_tasks(request: Request):
    ev = list(TASK_EVENTS)[-100:]
    ev.reverse()
    act = [o for o in ORDERS["list"] if o["status"] not in (3, 8)]
    return J({"events": ev, "now": now_s(), "orders": {"on": API_ON and API_EVERY["order"] > 0, "ts": now_s(ORDERS["ts"]) if ORDERS["ts"] else "",
                                                       "total": ORDERS["total"], "active": act, "shown": len(ORDERS["list"]), "err": API_ST["order"]["err"]}})


async def api_system(request: Request):
    now = time.time()
    chans = {k: {"count": v["count"], "today": v["today"], "ago": int(now - v["last"]) if v["last"] else None, "last": now_s(v["last"]) if v["last"] else ""}
             for k, v in CHAN.items()}
    days = []
    if os.path.isdir(LOG_DIR):
        for name in sorted(os.listdir(LOG_DIR), reverse=True):
            p = os.path.join(LOG_DIR, name)
            if os.path.isdir(p):
                days.append({"date": name, "files": [{"name": f, "kb": round(os.path.getsize(os.path.join(p, f)) / 1024, 1)} for f in sorted(os.listdir(p))]})
    return J({"uptime": int(now - START), "channels": chans, "paths": CFG["paths"], "rcs_url": CFG.get("public_host", "") + ":" + str(CFG["listen"]["port_rcs"]), "web_url": CFG.get("public_host", "") + ":" + str(CFG["listen"]["port_web"]), "retention_days": CFG["retention_days"], "days": days,
              "log_push": CFG.get("log_push", True), "log_api": CFG.get("log_api", True), "nodes": len(BY_CODE), "now": now_s(),
              "map": {"points": len(POINTS), "built": (MAP or {}).get("built", ""), "source": (MAP or {}).get("source", "")},
              "api": {"on": API_ON, "base": API.get("base", ""), "area_id": API.get("area_id"), "user": API.get("user", ""),
                      "items": {k: {"name": API_NAMES[k], "every": API_EVERY[k], "count": st["count"], "err": st["err"], "fail": st["fail"],
                                    "ago": int(now - st["ok"]) if st["ok"] else None, "last": now_s(st["ok"]) if st["ok"] else ""} for k, st in API_ST.items()}}})


async def api_history(request: Request):
    q = request.query_params
    date, kind = q.get("date") or day(), q.get("kind") or "incident"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or kind not in ("alarm", "agv", "task", "incident", "raw", "path", "order", "push", "api"):
        return J({"error": "tham số không hợp lệ"}, 400)
    rows = read_lines(os.path.join(LOG_DIR, date, kind + ".jsonl"), 2000)
    s = (q.get("q") or "").strip().lower()
    if s:
        rows = [r for r in rows if s in json.dumps(r, ensure_ascii=False).lower()]
    rows.reverse()
    return J({"date": date, "kind": kind, "count": len(rows), "rows": rows[:int(q.get("limit") or 200)]})


async def download(request: Request):
    d, f = request.path_params["date"], request.path_params["file"]
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) or not re.fullmatch(r"[a-z]+\.jsonl", f):
        return J({"error": "không hợp lệ"}, 400)
    p = os.path.join(LOG_DIR, d, f)
    return FileResponse(p, filename=f"{d}_{f}") if os.path.exists(p) else J({"error": "không có file"}, 404)


async def api_map(request: Request):
    return J({"ready": bool(MAP), "w": MAP["w"] if MAP else 0, "h": MAP["h"] if MAP else 0, "url": "/map/map.png?v=" + str(int(os.path.getmtime(os.path.join(MAP_DIR, "map.png")))) if MAP and os.path.exists(os.path.join(MAP_DIR, "map.png")) else ""})


async def map_file(request: Request):
    p = os.path.join(MAP_DIR, "map.png")
    return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"}) if os.path.exists(p) else J({"error": "chưa có ảnh bản đồ"}, 404)


async def index(request: Request):
    return FileResponse(os.path.join(HERE, "index.html"), headers={"Cache-Control": "no-store"})


# ---------------------------------------------------------------- nền: phát hiện mất tín hiệu, dọn log
async def watchdog():
    last_clean = 0
    while True:
        await asyncio.sleep(10)
        now = time.time()
        for name, r in ROBOTS.items():
            lost = now - r["ts"] > float(CFG.get("robot_stale_sec", 60))
            if lost and not r.get("lost"):
                r["lost"] = True
                incident("robot", "high", f"{name} MẤT TÍN HIỆU", f"Không có dữ liệu {int(now - r['ts'])} giây. Vị trí cuối: {robot_place(r)}", name)
            elif not lost:
                r["lost"] = False
        for name, r in ROBOTS.items():
            if r["status"] == 4 and not r.get("lost") and now - r.get("moved_ts", now) >= float(CFG.get("stuck_sec", 180)):
                if not r.get("stuck_flag"):
                    r["stuck_flag"] = True
                    incident("robot", "mid", f"{name} nghi kẹt: đứng yên khi đang chạy task", f"Đứng yên {dur_vi(now - r['moved_ts'])} · {robot_place(r)} · task {r['order']}", name)
        c = CHAN["agv"]
        if c["last"] and now - c["last"] > float(CFG.get("silence_warn_sec", 120)) and not FLAGS["silent"]:
            FLAGS["silent"] = True
            incident("system", "high", "RCS ngừng gửi dữ liệu trạng thái robot", f"Lần cuối {now_s(c['last'])}. Kiểm tra mạng/RCS hoặc tool này.")
        reload_now()
        if now - last_clean > 3600:
            last_clean = now
            cleanup_logs()


def restore_today():
    """Nạp lại log hôm nay sau khi khởi động lại để giao diện không trống."""
    d = os.path.join(LOG_DIR, day())
    for r in read_lines(os.path.join(d, "incident.jsonl"), 300):
        if "ts" in r:
            INCIDENTS.append(r)
    for r in read_lines(os.path.join(d, "task.jsonl"), 300):
        if "ts" in r:
            TASK_EVENTS.append(r)
            TASKS[r.get("order", "")] = r
    for r in read_lines(os.path.join(d, "order.jsonl"), 2000):
        if r.get("order"):
            ORDER_SEEN[r["order"]] = r.get("status")


@asynccontextmanager
async def lifespan(app):
    cleanup_logs()
    restore_today()
    incident("system", "low", "G8 Monitor khởi động", f"Đang chờ dữ liệu từ RCS tại {', '.join(CFG['paths'].values())}")
    tasks = [asyncio.create_task(watchdog())]
    if API_ON:
        tasks.append(asyncio.create_task(rcs_poller()))
        incident("system", "low", "Bật hỏi RCS định kỳ", f"{API['base']} · area {API.get('area_id')} · " + ", ".join(f"{k} mỗi {int(v)} giây" for k, v in API_EVERY.items() if v > 0))
    yield
    for t in tasks:
        t.cancel()


rcs_routes = []
routes = [Route("/", index), Route("/api/state", api_state), Route("/api/incidents", api_incidents), Route("/api/tasks", api_tasks),
          Route("/api/system", api_system), Route("/api/map", api_map), Route("/map/map.png", map_file), Route("/api/history", api_history), Route("/logs/{date}/{file}", download),
          Route("/api/rcs-auth", api_rcs_auth, methods=["POST"]), Route("/api/map-job", api_map_job, methods=["GET", "POST"]), Route("/api/map-file", api_map_file),
          Route("/api/map-update", api_map_update, methods=["POST"]), Route("/api/highbay", api_highbay, methods=["POST"])]
def make_receiver(kind):
    async def handler(request: Request):
        return await receive(request, kind)
    return handler


for kind, path in CFG["paths"].items():
    rcs_routes.append(Route(path, make_receiver(kind), methods=["POST", "PUT"]))
app = Starlette(routes=routes, lifespan=lifespan)               # cổng WEB: giao diện + API xem


async def rcs_ok(request: Request):
    return JSONResponse({"service": "G8 Monitor - cổng nhận dữ liệu RCS", "paths": CFG["paths"]})


rcs_app = Starlette(routes=[Route("/", rcs_ok)] + rcs_routes)       # cổng RCS: chỉ nhận 3 đường dẫn RCS đẩy lên

async def serve_all():
    host = CFG["listen"]["host"]
    servers = [uvicorn.Server(uvicorn.Config(rcs_app, host=host, port=int(CFG["listen"]["port_rcs"]), log_level="warning")),
               uvicorn.Server(uvicorn.Config(app, host=host, port=int(CFG["listen"]["port_web"]), log_level="warning"))]
    await asyncio.gather(*[sv.serve() for sv in servers])


if __name__ == "__main__":
    asyncio.run(serve_all())
