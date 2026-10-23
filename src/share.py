"""Trang kéo file cổng 5505: liệt kê file trong thư mục chia sẻ (mặc định share/, không đưa lên git) để máy xem từ xa tải về.
Bên máy chủ chỉ cần chép file vào thư mục đó; trang không tự làm mới, người xem bấm tải lại trang.
Tải theo khúc bằng header Range giống nút tải map, khúc lỗi thì máy xem thử lại khúc đó.
Cần đăng nhập: cùng mật khẩu và phiên với trang quản trị 5504 (admin.py).
"""
import os
import re

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Route

import admin

HERE = os.path.dirname(os.path.abspath(__file__))


def J(d, status=200):
    return JSONResponse(d, status_code=status, headers={"Cache-Control": "no-store"})


def make_app(folder, version, static_dir):
    folder = os.path.realpath(folder)
    os.makedirs(folder, exist_ok=True)

    def resolve(name):
        """Đường dẫn tương đối (dùng /) → file thật trong thư mục chia sẻ; None nếu ra ngoài thư mục, file ẩn hoặc không có."""
        parts = [p for p in (name or "").replace("\\", "/").split("/") if p]
        if not parts or any(p.startswith(".") for p in parts):
            return None
        p = os.path.realpath(os.path.join(folder, *parts))
        if not p.startswith(folder + os.sep) or not os.path.isfile(p):
            return None
        return p

    async def page(request):
        with open(os.path.join(HERE, "share.html"), encoding="utf-8") as f:
            return Response(f.read().replace("{{VERSION}}", version), media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})

    async def static(request):
        name = request.path_params["name"]
        p = os.path.join(static_dir, name)
        if not re.fullmatch(r"[a-z0-9_-]+\.(png|svg|ico)", name) or not os.path.exists(p):
            return J({"error": "không có file"}, 404)
        return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})

    async def files(request):
        if not admin.authed(request):
            return J({"error": "Cần đăng nhập", "login": True}, 401)
        out = []
        for d, dirs, names in os.walk(folder):
            dirs[:] = [x for x in dirs if not x.startswith(".")]
            for n in names:
                if n.startswith("."):
                    continue
                p = os.path.join(d, n)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                out.append({"name": os.path.relpath(p, folder).replace(os.sep, "/"), "size": st.st_size, "mtime": int(st.st_mtime)})
        out.sort(key=lambda x: -x["mtime"])
        return J({"folder": folder, "files": out})

    async def file(request: Request):
        """Tải một file. Có header Range thì trả đúng khúc đó (206). v = mtime lúc liệt kê: file đã bị thay thì báo 409."""
        if not admin.authed(request):
            return J({"error": "Cần đăng nhập", "login": True}, 401)
        name = request.query_params.get("name") or ""
        path = resolve(name)
        if not path:
            return J({"error": "không thấy file trên máy chủ, tải lại trang"}, 404)
        st = os.stat(path)
        v = request.query_params.get("v")
        if v and v != str(int(st.st_mtime)):
            return J({"error": "file trên máy chủ đã thay đổi, tải lại trang rồi bấm tải lại"}, 409)
        size = st.st_size
        m = re.fullmatch(r"bytes=(\d+)-(\d*)", (request.headers.get("range") or "").strip())
        if not m:
            return FileResponse(path, filename=os.path.basename(path), headers={"Accept-Ranges": "bytes", "Cache-Control": "no-store"})
        a = int(m.group(1))
        b = min(int(m.group(2)) if m.group(2) else size - 1, size - 1)
        if a > b:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        with open(path, "rb") as f:
            f.seek(a)
            data = f.read(b - a + 1)
        return Response(data, status_code=206, media_type="application/octet-stream",
                        headers={"Content-Range": f"bytes {a}-{b}/{size}", "Accept-Ranges": "bytes", "Cache-Control": "no-store"})

    return Starlette(routes=[Route("/", page), Route("/static/{name}", static), Route("/api/files", files), Route("/api/file", file),
                             Route("/api/login", admin.login, methods=["POST"]), Route("/api/logout", admin.logout, methods=["POST"])])
