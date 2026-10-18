"""Nạp cấu hình: config.example.json (mặc định, có trên git) + config.json (riêng từng máy) đè lên.
Khóa mới thêm vào mẫu tự có trên máy cũ mà không phải sửa config.json. rcs_api.base để trống thì dùng base của mẫu
(tắt hẳn bằng "enabled": false).
"""
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # thư mục gốc project
EXAMPLE = os.path.join(ROOT, "config.example.json")
PATH = os.environ.get("MON_CONFIG") or os.path.join(ROOT, "config.json")


def _read(p):
    with open(p, encoding="utf-8-sig") as f:
        return json.load(f)


def _merge(base, over):
    out = dict(base)
    for k, v in over.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load():
    if not os.path.exists(PATH):                                     # máy mới clone: tạo config.json từ mẫu
        shutil.copy(EXAMPLE, PATH)
    example = _read(EXAMPLE) if os.path.exists(EXAMPLE) else {}
    cfg = _merge(example, _read(PATH))
    api = cfg.setdefault("rcs_api", {})
    if not api.get("base"):
        api["base"] = (example.get("rcs_api") or {}).get("base", "")
    return cfg


def save_rcs_auth(user, password):
    """Ghi user/password RCS vào config.json của máy (không đưa lên git)."""
    local = _read(PATH)
    local.setdefault("rcs_api", {}).update(user=user, password=password)
    _write(local)


def save_section(key, value):
    """Ghi đè một mục (vd "telegram", "alerts") trong config.json của máy. Dùng cho trang quản trị."""
    local = _read(PATH)
    local[key] = value
    _write(local)


def _write(local):
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(local, f, ensure_ascii=False, indent=2)
    os.replace(tmp, PATH)
