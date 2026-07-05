import copy
import json
import os
import threading

_DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "config.default.json")
_USER_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")

_lock = threading.Lock()
_cache = None


def _load_default():
    with open(_DEFAULT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = copy.deepcopy(v)
    return result


def _load():
    global _cache
    if _cache is not None:
        return _cache
    cfg = _load_default()
    if os.path.exists(_USER_PATH):
        try:
            with open(_USER_PATH, "r", encoding="utf-8") as f:
                user = json.load(f)
            cfg = _deep_merge(cfg, user)
        except (json.JSONDecodeError, OSError):
            pass
    _cache = cfg
    return cfg


def _persist(cfg):
    global _cache
    _cache = cfg
    with _lock:
        tmp = _USER_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, _USER_PATH)


def get(path=None, default=None):
    cfg = _load()
    if not path:
        return cfg
    node = cfg
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def set(path, value):
    cfg = _load()
    node = cfg
    parts = path.split(".")
    for part in parts[:-1]:
        if part not in node or not isinstance(node[part], dict):
            node[part] = {}
        node = node[part]
    node[parts[-1]] = value
    _persist(cfg)
    return value


def all():
    return _load()


def save_full(cfg_in):
    base = _load_default()
    merged = _deep_merge(base, cfg_in)
    _persist(merged)
    return merged


def reload():
    global _cache
    _cache = None
    return _load()
