"""Trang quản trị cổng 5504 (đăng nhập dùng chung với trang kéo file 5505): bật/tắt Telegram, cấu hình bot, ngưỡng và danh sách lỗi được đẩy tin. Cần mật khẩu (cố định trong code).
Phiên đăng nhập là cookie ngẫu nhiên giữ trong bộ nhớ (khởi động lại tool thì phải đăng nhập lại). Sai mật khẩu 5 lần thì khóa IP đó 5 phút.
"""
import asyncio
import hmac
import html
import os
import re
import secrets
import time

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

import notify

ADMIN_PASSWORD = "G8@Admin2026"       # mật khẩu trang quản trị — đổi ở đây rồi khởi động lại tool
SESSION_HOURS = 12
HERE = os.path.dirname(os.path.abspath(__file__))
SESSIONS = {}                         # token -> hết hạn
FAILS = {}                            # ip -> [số lần sai, khóa đến]


def J(d, status=200):
    return JSONResponse(d, status_code=status, headers={"Cache-Control": "no-store"})


def authed(request):
    t = request.cookies.get("g8adm") or ""
    exp = SESSIONS.get(t)
    if exp and exp > time.time():
        return True
    SESSIONS.pop(t, None)
    return False


def mask(token):
    return (token[:6] + "…" + token[-4:]) if len(token) > 12 else ("đã nhập" if token else "")


def num(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    v = min(max(v, lo), hi)
    return int(v) if v == int(v) else v


async def login(request):
    """Đăng nhập chung cho trang quản trị 5504 và trang kéo file 5505 (cùng mật khẩu, cùng phiên)."""
    ip = request.client.host if request.client else ""
    f = FAILS.get(ip, [0, 0])
    if f[1] > time.time():
        return J({"error": f"Sai mật khẩu quá nhiều lần, thử lại sau {int(f[1] - time.time()) // 60 + 1} phút"}, 429)
    try:
        pw = str((await request.json()).get("password") or "")
    except ValueError:
        pw = ""
    if not hmac.compare_digest(pw.encode("utf-8"), ADMIN_PASSWORD.encode("utf-8")):
        f[0] += 1
        if f[0] >= 5:
            f[:] = [0, time.time() + 300]
        FAILS[ip] = f
        await asyncio.sleep(1)
        return J({"error": "Sai mật khẩu"}, 401)
    FAILS.pop(ip, None)
    for k in [k for k, v in SESSIONS.items() if v < time.time()]:
        SESSIONS.pop(k, None)
    tok = secrets.token_urlsafe(32)
    SESSIONS[tok] = time.time() + SESSION_HOURS * 3600
    r = J({"ok": True})
    r.set_cookie("g8adm", tok, max_age=SESSION_HOURS * 3600, httponly=True, samesite="strict")
    return r


async def logout(request):
    SESSIONS.pop(request.cookies.get("g8adm") or "", None)
    r = J({"ok": True})
    r.delete_cookie("g8adm")
    return r


def make_app(noti, version, static_dir, extra):
    async def page(request):
        with open(os.path.join(HERE, "admin.html"), encoding="utf-8") as f:
            return Response(f.read().replace("{{VERSION}}", version), media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})

    async def static(request):
        name = request.path_params["name"]
        p = os.path.join(static_dir, name)
        if not re.fullmatch(r"[a-z0-9_-]+\.(png|svg|ico)", name) or not os.path.exists(p):
            return J({"error": "không có file"}, 404)
        return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})

    def state():
        t = noti.tg()
        rules = []
        for d in notify.RULES:
            cur = noti.rule(d["id"])
            rules.append({"id": d["id"], "code": d["code"], "name": d["name"], "start": d["start"], "stop": d["stop"], "end": d["end"],
                          "on": bool(cur["on"]), "night": bool(cur.get("night")),
                          **{k: cur[k] for k in notify.PARAMS if k in d}})
        return {"version": version, "telegram": {**{k: v for k, v in t.items() if k != "token"}, "token": mask(t["token"]), "token_set": bool(t["token"])},
                "rules": rules, "ready": noti.ready(), "stat": noti.stat, "queue": noti.queue.qsize(), "open": noti.view(),
                "recent": list(noti.recent)[-50:][::-1], **extra()}

    async def settings(request):
        if not authed(request):
            return J({"error": "Cần đăng nhập", "login": True}, 401)
        if request.method == "GET":
            return J(state())
        try:
            d = await request.json()
        except ValueError:
            return J({"error": "dữ liệu không hợp lệ"}, 400)
        t, old = d.get("telegram") or {}, noti.tg()
        token = str(t.get("token") or "").strip()
        if token and not re.fullmatch(r"\d{5,}:[\w-]{20,}", token):
            return J({"error": "Token bot không đúng dạng 123456789:ABC… (lấy từ @BotFather)"}, 400)
        chat = str(t.get("chat_id") or "").strip()
        if chat and not re.fullmatch(r"-?\d{3,}|@\w{4,}", chat):
            return J({"error": "Chat ID phải là số (nhóm thường là số âm, vd -1001234567890) hoặc @tenkenh"}, 400)
        for k in ("night_start", "night_end"):
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(t.get(k) or "")):
                return J({"error": "Giờ nghỉ phải dạng HH:MM, vd 00:00 và 07:00"}, 400)
        tg = {"enabled": bool(t.get("enabled")), "token": token or old["token"], "chat_id": chat, "prefix": str(t.get("prefix") or "")[:20],
              "remind_min": num(t.get("remind_min"), 0, 1440, 30), "stale_min": num(t.get("stale_min"), 5, 1440, 120),
              "send_end": bool(t.get("send_end", True)), "night_start": t["night_start"], "night_end": t["night_end"]}
        if t.get("clear_token"):
            tg["token"] = ""
        rules = {}
        for rid, r in (d.get("rules") or {}).items():
            if rid not in notify.RULE:
                continue
            base = notify.RULE[rid]
            x = {"on": bool(r.get("on")), "night": bool(r.get("night"))}
            for k, lim in (("delay", 86400), ("quiet", 86400), ("low", 100), ("ok", 100), ("fails", 100)):
                if k in base:
                    x[k] = num(r.get(k), 0 if k != "fails" else 1, lim, base[k])
            rules[rid] = x
        noti.update(tg, {**(noti.cfg.get("alerts") or {}), **rules})
        return J({"ok": True, **state()})

    async def test(request):
        if not authed(request):
            return J({"error": "Cần đăng nhập", "login": True}, 401)
        t = noti.tg()
        if not (t["token"] and t["chat_id"]):
            return J({"error": "Chưa nhập token bot hoặc chat ID"}, 400)
        try:
            await asyncio.to_thread(notify.api, t["token"], "sendMessage", {"chat_id": t["chat_id"], "parse_mode": "HTML",
                                    "text": f"✅ <b>[{html.escape(t.get('prefix') or 'G8')}] Tin thử từ G8 Monitor {version}</b>\nBot đã gửi được vào nhóm này. {time.strftime('%d/%m/%Y %H:%M:%S')}"})
        except notify.TgError as e:
            return J({"error": f"Telegram báo lỗi: {e}"}, 400)
        return J({"ok": True})

    async def chats(request):
        if not authed(request):
            return J({"error": "Cần đăng nhập", "login": True}, 401)
        t = noti.tg()
        if not t["token"]:
            return J({"error": "Lưu token bot trước"}, 400)
        try:
            return J({"chats": await asyncio.to_thread(notify.find_chats, t["token"])})
        except notify.TgError as e:
            return J({"error": f"Telegram báo lỗi: {e}"}, 400)

    return Starlette(routes=[Route("/", page), Route("/static/{name}", static), Route("/api/login", login, methods=["POST"]),
                             Route("/api/logout", logout, methods=["POST"]), Route("/api/settings", settings, methods=["GET", "POST"]),
                             Route("/api/test", test, methods=["POST"]), Route("/api/chats", chats, methods=["POST"])])
