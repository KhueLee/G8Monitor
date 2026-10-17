"""Gọi API của RCS/ICS (tài liệu Interface Protocol V3.0.6, mục 4.1). Chỉ dùng các API ĐỌC:
  getRobotTaskPath (4.1.2.5), getOrderList (4.1.1.7), topologyList (4.1.5.1).
Cấu hình trong config.json -> "rcs_api". Mọi API là HTTP POST JSON, cổng mặc định 7000.
"""
import base64
import hashlib
import json
import time
import urllib.error
import urllib.request

PATHS = {"path": "/ics/out/getRobotTaskPath", "order": "/ics/out/task/getOrderList", "topology": "/ics/out/topologyList"}


class RcsError(Exception):
    pass


class RcsAuthError(RcsError):
    """RCS bật xác thực WSSE và từ chối (thiếu hoặc sai user/password)."""


AUTH_WORDS = ("auth", "token", "login", "unauthor", "forbidden", "permission", "password", "wsse", "认证", "鉴权", "登录", "权限", "密码")


def wsse(user, password):
    """Chuỗi Authorization WSSE (mục 2.3): user:timestamp:base64(sha1(timestamp + password))."""
    ts = str(int(time.time()))
    digest = base64.b64encode(hashlib.sha1((ts + password).encode("utf-8")).digest()).decode()
    return f"{user}:{ts}:{digest}"


def call(api_cfg, kind, body, trace=None):
    """POST tới RCS, trả về phần "data" khi code=1000; lỗi mạng hoặc code khác thì raise RcsError (RcsAuthError nếu bị từ chối xác thực).
    trace (dict) nếu có sẽ được điền url, http, phản hồi gốc, thời gian gọi để ghi log."""
    trace = {} if trace is None else trace
    base = (api_cfg.get("base") or "").rstrip("/")
    if not base:
        raise RcsError("chưa khai rcs_api.base trong config.json")
    url = base + PATHS[kind]
    trace.update(url=url, req=body, auth=bool(api_cfg.get("user")))
    headers = {"Content-Type": "application/json"}
    if api_cfg.get("user"):
        headers["Authorization"] = wsse(api_cfg["user"], api_cfg.get("password", ""))
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=float(api_cfg.get("timeout_sec", 8))) as r:
            trace["http"] = r.status
            raw = r.read()
    except urllib.error.HTTPError as e:
        trace.update(http=e.code, ms=int((time.time() - t0) * 1000), resp=e.read()[:4000].decode("utf-8", "replace"))
        if e.code in (401, 403):
            raise RcsAuthError(f"{PATHS[kind]}: RCS từ chối xác thực (HTTP {e.code}), cần user/password") from e
        raise RcsError(f"{PATHS[kind]}: HTTP {e.code} {e.reason}") from e
    except Exception as e:
        trace["ms"] = int((time.time() - t0) * 1000)
        raise RcsError(f"không gọi được {PATHS[kind]}: {e}") from e
    trace["ms"] = int((time.time() - t0) * 1000)
    try:
        res = json.loads(raw.decode("utf-8-sig"))
    except ValueError as e:
        trace["resp"] = raw[:4000].decode("utf-8", "replace")
        raise RcsError(f"{PATHS[kind]} trả về không phải JSON: {raw[:200]!r}") from e
    trace["resp"] = res
    if str(res.get("code")) != "1000":
        msg = f"{PATHS[kind]} báo lỗi code={res.get('code')} {res.get('desc') or ''}".strip()
        if str(res.get("code")) in ("401", "403") or any(w in str(res.get("desc") or "").lower() for w in AUTH_WORDS):
            raise RcsAuthError(msg + " (cần user/password)")
        raise RcsError(msg)
    return res.get("data")


def download(url, timeout=120):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()
