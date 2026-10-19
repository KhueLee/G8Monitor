"""Đẩy cảnh báo qua Telegram. Mỗi lỗi là một "điều kiện" (luật + thiết bị): main.py gọi raise_() khi thấy lỗi, clear() khi hết.
tick() (gọi mỗi vài giây) quyết định gửi: lỗi kéo dài đủ ngưỡng (delay) mới gửi tin BẮT ĐẦU, hết thì gửi tin KẾT THÚC trả lời vào tin bắt đầu,
chưa hết sau remind_min phút thì nhắc. Lỗi hết trước ngưỡng thì không gửi gì. Cấu hình ở config.json -> "telegram", "alerts" (trang quản trị cổng 5504).
"""
import asyncio
import html
import json
import time
import urllib.error
import urllib.request
from collections import deque

# end: "status" = hết khi RCS/trạng thái báo hết; "quiet" = hết khi không lặp lại trong quiet_sec giây (RCS không gửi tin hết)
# alarm=True: điều kiện đến từ cảnh báo RCS, nếu RCS không bao giờ báo hết thì tự đóng sau stale_min phút
RULES = [
    {"id": "collision", "code": "A1", "name": "Va chạm", "delay": 0, "end": "status", "alarm": True,
     "start": "Cảnh báo RCS loại 28 (Va chạm)", "stop": "RCS báo hết (alarmStatus=1)"},
    {"id": "pallet", "code": "A2", "name": "Nhận diện pallet lỗi (xe nâng)", "delay": 0, "end": "quiet", "quiet": 600, "alarm": True,
     "start": "Cảnh báo RCS loại 50 (mã 25216, 25222, 25131…)", "stop": "Xe đi được hơn 0,5 m, hoặc không lặp lại trong 'Hết sau'"},
    {"id": "nav", "code": "A3", "name": "Lỗi dẫn đường", "delay": 0, "end": "status", "alarm": True,
     "start": "Cảnh báo RCS loại 8 (RobotLocationException)", "stop": "RCS báo hết"},
    {"id": "device", "code": "A4", "name": "Thiết bị hỏng", "delay": 0, "end": "status", "alarm": True,
     "start": "Cảnh báo RCS loại 2", "stop": "RCS báo hết"},
    {"id": "map_update", "code": "A5", "name": "Cập nhật bản đồ lỗi", "delay": 0, "end": "quiet", "quiet": 600, "alarm": True,
     "start": "Cảnh báo RCS loại 11 (FileUnmatch…)", "stop": "Không lặp lại trong 'Hết sau'"},
    {"id": "charge_fail", "code": "A6", "name": "Sạc lỗi", "delay": 60, "end": "status", "alarm": True,
     "start": "Cảnh báo RCS loại 21, kèm mã lỗi 72xx", "stop": "RCS báo hết, hoặc robot vào sạc được, hoặc robot nhận task rời cọc"},
    {"id": "task_fail", "code": "A7", "name": "Task gửi lỗi / chạy lỗi", "delay": 0, "end": "status",
     "start": "Task có trạng thái 5 (gửi lỗi) hoặc 7 (chạy lỗi)", "stop": "Task chuyển trạng thái khác (hoàn thành, hủy…)"},
    {"id": "offline", "code": "A8", "name": "Robot offline (trong giờ ca)", "delay": 60, "end": "status", "night": True,
     "start": "state = Offline liên tục quá ngưỡng, ngoài khung giờ nghỉ", "stop": "Robot online lại"},
    {"id": "fault", "code": "A9", "name": "Robot báo LỖI", "delay": 0, "end": "status",
     "start": "Mã trạng thái robot = 2 (Fault)", "stop": "Mã trạng thái khác 2"},
    {"id": "lost", "code": "A10", "name": "Mất tín hiệu robot", "delay": 60, "end": "status",
     "start": "Không có dữ liệu của robot quá ngưỡng", "stop": "Có dữ liệu trở lại"},
    {"id": "battery", "code": "A11", "name": "Pin thấp", "delay": 0, "end": "status", "low": 20, "ok": 25,
     "start": "Pin dưới 'Pin thấp' % và không sạc", "stop": "Robot vào sạc, hoặc pin từ 'Pin đủ' % trở lên"},
    {"id": "rcs_silent", "code": "A12", "name": "RCS ngừng gửi dữ liệu", "delay": 120, "end": "status",
     "start": "Không có bản tin trạng thái robot quá ngưỡng", "stop": "Bản tin đến trở lại"},
    {"id": "api_fail", "code": "A13", "name": "Không gọi được API RCS", "delay": 0, "end": "status", "fails": 3,
     "start": "Số lần gọi lỗi liên tiếp đạt 'Số lần lỗi'", "stop": "Gọi thành công lại"},
    {"id": "startup", "code": "A14", "name": "Monitor khởi động lại", "delay": 0, "end": "once",
     "start": "Mỗi lần G8 Monitor khởi động", "stop": "—"},
    {"id": "label", "code": "A15", "name": "Không thấy mã kệ / mã đường", "delay": 0, "end": "quiet", "quiet": 600, "alarm": True,
     "start": "Cảnh báo RCS loại 22 LableNotFound, tách theo lúc lấy kệ / trả kệ / trên đường", "stop": "Cùng robot, cùng điểm không lặp lại trong 'Hết sau'"},
    {"id": "stuck", "code": "B1", "name": "Nghi kẹt (đứng yên khi chạy task)", "delay": 300, "end": "status",
     "start": "Đang chạy task, di chuyển dưới 0,5 m quá ngưỡng (tính từ lúc nhận task)", "stop": "Đi được hơn 0,5 m hoặc hết chạy task"},
    {"id": "path", "code": "B2", "name": "Đường đi bất thường", "delay": 60, "end": "status", "alarm": True,
     "start": "Cảnh báo RCS loại 23 chưa hết sau ngưỡng", "stop": "RCS báo hết"},
    {"id": "shelf", "code": "B3", "name": "Kệ bất thường", "delay": 60, "end": "status", "alarm": True,
     "start": "Cảnh báo RCS loại 22 chưa hết sau ngưỡng", "stop": "RCS báo hết"},
    {"id": "obstacle", "code": "B4", "name": "Có vật cản", "delay": 180, "end": "status", "alarm": True,
     "start": "Cảnh báo RCS loại 12 chưa hết sau ngưỡng", "stop": "RCS báo hết"},
    {"id": "load", "code": "B5", "name": "Tải bất thường", "delay": 60, "end": "status", "alarm": True,
     "start": "Cảnh báo RCS loại 25 chưa hết sau ngưỡng", "stop": "RCS báo hết"},
    {"id": "charger", "code": "B6", "name": "Cọc sạc mất giao tiếp", "delay": 300, "end": "quiet", "quiet": 300, "alarm": True,
     "start": "Cọc sạc (1080–1083…) báo lỗi lặp lại liên tục quá ngưỡng", "stop": "Không có lỗi mới trong 'Hết sau'"},
]
RULE = {r["id"]: r for r in RULES}
ALARM_RULE = {28: "collision", 50: "pallet", 8: "nav", 2: "device", 11: "map_update", 21: "charge_fail",
              23: "path", 22: "shelf", 12: "obstacle", 25: "load"}
PARAMS = ("delay", "quiet", "low", "ok", "fails")          # tham số số của luật, sửa được trên trang quản trị
TG_DEFAULT = {"enabled": False, "token": "", "chat_id": "", "remind_min": 30, "stale_min": 120, "send_end": True,
              "night_start": "00:00", "night_end": "07:00", "prefix": "G8"}


def dur(sec):
    sec = int(sec)
    if sec < 60:
        return f"{sec} giây"
    if sec < 3600:
        return f"{sec // 60} phút" + (f" {sec % 60} giây" if sec % 60 and sec < 600 else "")
    return f"{sec // 3600} giờ {sec % 3600 // 60} phút"


def hm(s, default):
    try:
        h, m = str(s).split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return h * 60 + m
    except ValueError:
        pass
    return default


def night_info(now, start_s, end_s):
    """(đang trong giờ nghỉ?, mốc giờ nghỉ kết thúc gần nhất <= now). start == end thì coi như không có giờ nghỉ."""
    a, b = hm(start_s, 0), hm(end_s, 420)
    lt = time.localtime(now)
    cur = lt.tm_hour * 60 + lt.tm_min
    midnight = now - (lt.tm_hour * 3600 + lt.tm_min * 60 + lt.tm_sec)
    inside = a != b and ((a <= cur < b) if a < b else (cur >= a or cur < b))
    last_end = midnight + b * 60
    if last_end > now:
        last_end -= 86400
    return inside, last_end


class Notifier:
    def __init__(self, cfg, save, log):
        self.cfg, self.save, self.log = cfg, save, log      # cfg: dict cấu hình đang chạy; save(key, value): ghi config.json; log(kind, rec)
        self.open = {}                                      # (luật, thiết bị) -> điều kiện đang mở
        self.queue = asyncio.Queue()
        self.recent = deque(maxlen=200)
        self.stat = {"sent": 0, "fail": 0, "last_ok": 0, "last_err": "", "last_err_ts": 0, "dropped": 0}

    # ------------------------------------------------ cấu hình
    def tg(self):
        return {**TG_DEFAULT, **(self.cfg.get("telegram") or {})}

    def rule(self, rid):
        return {**RULE[rid], **{"on": True, "night": RULE[rid].get("night", False)}, **((self.cfg.get("alerts") or {}).get(rid) or {})}

    def update(self, tg=None, rules=None):
        if tg is not None:
            self.cfg["telegram"] = tg
            self.save("telegram", tg)
        if rules is not None:
            self.cfg["alerts"] = rules
            self.save("alerts", rules)

    def ready(self):
        t = self.tg()
        return bool(t["enabled"] and t["token"] and t["chat_id"])

    # ------------------------------------------------ điều kiện lỗi
    def raise_(self, rid, dev, title, detail="", since=None):
        now = time.time()
        c = self.open.get((rid, dev))
        if c is None:
            self.open[(rid, dev)] = {"rule": rid, "dev": dev, "title": title, "detail": detail, "since": since or now, "seen": now,
                                     "fired": 0, "msg": None, "remind": 0}
        else:
            c["seen"], c["title"] = now, title
            if detail:
                c["detail"] = detail

    def get(self, rid, dev):
        return self.open.get((rid, dev))

    def clear(self, rid, dev, note=""):
        c = self.open.pop((rid, dev), None)
        if c and c["fired"] and self.tg()["send_end"]:
            r, now = self.rule(rid), time.time()
            self.send(f"✅ <b>Hết: {html.escape(c['title'])}</b>\nKéo dài {dur(now - c['since'])}" + (f" · {html.escape(note)}" if note else "") +
                      f"\n<i>{r['code']} · kết thúc {time.strftime('%H:%M:%S', time.localtime(now))}</i>", c["msg"], ("end", c))

    def drop_unfired(self, rid):
        """Bỏ im lặng các điều kiện của luật chưa kịp gửi tin (vd mất tín hiệu từng robot khi cả RCS ngừng gửi)."""
        for key in [k for k, c in self.open.items() if k[0] == rid and not c["fired"]]:
            self.open.pop(key, None)

    def once(self, rid, title, detail=""):
        r = self.rule(rid)
        if r["on"]:
            self.send(f"ℹ️ <b>{html.escape(title)}</b>" + (f"\n{html.escape(detail)}" if detail else "") + f"\n<i>{r['code']} · {time.strftime('%d/%m %H:%M:%S')}</i>", None, ("once", None))

    def tick(self):
        now, t = time.time(), self.tg()
        night, night_end = night_info(now, t["night_start"], t["night_end"])
        for key, c in list(self.open.items()):
            r = self.rule(c["rule"])
            if r["end"] == "quiet" and now - c["seen"] >= float(r.get("quiet", 300)):
                self.clear(*key, note=f"không lặp lại {dur(r.get('quiet', 300))}")
                continue
            if r.get("alarm") and r["end"] == "status" and now - c["seen"] >= float(t["stale_min"]) * 60:
                self.clear(*key, note=f"RCS không báo hết sau {dur(now - c['seen'])}, tự đóng")
                continue
            if not c["fired"]:
                if not r["on"]:
                    continue
                start = c["since"]
                if r.get("night"):
                    if night:
                        continue
                    start = max(start, night_end)
                if now - start >= float(r.get("delay", 0)):
                    self.fire(c, r, now)
            elif not c["remind"] and float(t["remind_min"]) > 0 and now - c["fired"] >= float(t["remind_min"]) * 60 and not (r.get("night") and night):
                c["remind"] = now
                self.send(f"⏰ <b>Chưa hết sau {dur(now - c['since'])}: {html.escape(c['title'])}</b>" + (f"\n{html.escape(c['detail'])}" if c["detail"] else ""),
                          c["msg"], ("remind", c))

    def fire(self, c, r, now):
        c["fired"] = now
        icon = "🔴" if r["code"].startswith("A") else "🟠"
        self.send(f"{icon} <b>{html.escape(c['title'])}</b>" + (f"\n{html.escape(c['detail'])}" if c["detail"] else "") +
                  f"\n<i>{r['code']} · {r['name']} · bắt đầu {time.strftime('%H:%M:%S', time.localtime(c['since']))}</i>", None, ("start", c))

    def view(self):
        now = time.time()
        return [{"code": RULE[c["rule"]]["code"], "rule": c["rule"], "dev": c["dev"], "title": c["title"], "detail": c["detail"],
                 "age": int(now - c["since"]), "fired": bool(c["fired"])} for c in sorted(self.open.values(), key=lambda c: c["since"])]

    # ------------------------------------------------ gửi Telegram (hàng đợi, 1 tin/giây, thử lại khi lỗi mạng / bị giới hạn)
    def send(self, text, reply_to, ctx):
        t = self.tg()
        prefix = f"[{html.escape(t['prefix'])}] " if t.get("prefix") else ""
        text = prefix + text
        rec = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), "kind": ctx[0], "text": text}
        if not self.ready():
            rec["result"] = "không gửi (Telegram đang tắt hoặc thiếu token/chat_id)"
            self._done(rec)
            return
        if self.queue.qsize() >= 300:
            self.stat["dropped"] += 1
            rec["result"] = "bỏ (hàng đợi đầy)"
            self._done(rec)
            return
        self.queue.put_nowait((text, reply_to, ctx, rec))

    def _done(self, rec):
        self.recent.append(rec)
        self.log("notify", rec)

    async def worker(self):
        while True:
            text, reply_to, ctx, rec = await self.queue.get()
            t = self.tg()
            for attempt in range(4):
                try:
                    res = await asyncio.to_thread(api, t["token"], "sendMessage", {
                        "chat_id": t["chat_id"], "text": text[:4000], "parse_mode": "HTML", "disable_web_page_preview": True,
                        **({"reply_to_message_id": reply_to, "allow_sending_without_reply": True} if reply_to else {})})
                    if ctx[0] == "start" and ctx[1] is not None:
                        ctx[1]["msg"] = (res or {}).get("message_id")
                    self.stat.update(sent=self.stat["sent"] + 1, last_ok=time.time())
                    rec["result"] = "đã gửi"
                    break
                except TgError as e:
                    rec["result"] = f"lỗi: {e}"
                    self.stat.update(last_err=str(e), last_err_ts=time.time())
                    if e.retry_after:
                        await asyncio.sleep(min(e.retry_after, 60))
                    elif e.permanent:
                        break
                    else:
                        await asyncio.sleep(5 * (attempt + 1))
            if rec["result"] != "đã gửi":
                self.stat["fail"] += 1
            self._done(rec)
            await asyncio.sleep(1)


class TgError(Exception):
    def __init__(self, msg, retry_after=0, permanent=False):
        super().__init__(msg)
        self.retry_after, self.permanent = retry_after, permanent


def api(token, method, body=None, timeout=12):
    """Gọi Bot API của Telegram. Trả về phần "result"; lỗi thì raise TgError (permanent=True nếu sai token/chat_id, thử lại vô ích)."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    req = urllib.request.Request(url, data=json.dumps(body or {}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read().decode("utf-8"))
        except ValueError:
            raise TgError(f"HTTP {e.code}", permanent=e.code in (401, 403, 404)) from e
    except Exception as e:
        raise TgError(f"không kết nối được api.telegram.org: {e}") from e
    if not res.get("ok"):
        code = res.get("error_code")
        raise TgError(f"{code} {res.get('description', '')}".strip(), (res.get("parameters") or {}).get("retry_after", 0), code in (400, 401, 403, 404))
    return res.get("result")


def find_chats(token):
    """Các nhóm/người đã nhắn hoặc thêm bot gần đây (getUpdates) -> để chọn chat_id."""
    out = {}
    for u in api(token, "getUpdates", {"limit": 100, "allowed_updates": ["message", "my_chat_member", "channel_post"]}) or []:
        for k in ("message", "my_chat_member", "channel_post"):
            ch = (u.get(k) or {}).get("chat")
            if ch:
                out[ch["id"]] = {"id": ch["id"], "type": ch.get("type"), "title": ch.get("title") or ch.get("username") or
                                 " ".join(filter(None, [ch.get("first_name"), ch.get("last_name")]))}
    return list(out.values())
