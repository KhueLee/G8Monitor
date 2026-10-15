"""Gọi API của RCS/ICS (tài liệu Interface Protocol V3.0.6, mục 4.1). Chỉ dùng các API ĐỌC:
  getRobotTaskPath (4.1.2.5), getOrderList (4.1.1.7), topologyList (4.1.5.1).
Cấu hình trong config.json -> "rcs_api". Mọi API là HTTP POST JSON, cổng mặc định 7000.
"""
import base64
import hashlib
import json
import time
import urllib.request

PATHS = {"path": "/ics/out/getRobotTaskPath", "order": "/ics/out/task/getOrderList", "topology": "/ics/out/topologyList"}


class RcsError(Exception):
    pass


def wsse(user, password):
    """Chuỗi Authorization WSSE (mục 2.3): user:timestamp:base64(sha1(timestamp + password))."""
    ts = str(int(time.time()))
    digest = base64.b64encode(hashlib.sha1((ts + password).encode("utf-8")).digest()).decode()
    return f"{user}:{ts}:{digest}"


def call(api_cfg, kind, body):
    """POST tới RCS, trả về phần "data" khi code=1000; lỗi mạng hoặc code khác thì raise RcsError."""
    base = (api_cfg.get("base") or "").rstrip("/")
    if not base:
        raise RcsError("chưa khai rcs_api.base trong config.json")
    headers = {"Content-Type": "application/json"}
    if api_cfg.get("user"):
        headers["Authorization"] = wsse(api_cfg["user"], api_cfg.get("password", ""))
    req = urllib.request.Request(base + PATHS[kind], data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=float(api_cfg.get("timeout_sec", 8))) as r:
            raw = r.read()
    except Exception as e:
        raise RcsError(f"không gọi được {PATHS[kind]}: {e}") from e
    try:
        res = json.loads(raw.decode("utf-8-sig"))
    except ValueError as e:
        raise RcsError(f"{PATHS[kind]} trả về không phải JSON: {raw[:200]!r}") from e
    if str(res.get("code")) != "1000":
        raise RcsError(f"{PATHS[kind]} báo lỗi code={res.get('code')} {res.get('desc') or ''}".strip())
    return res.get("data")


def download(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()
