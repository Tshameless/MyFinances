"""磁盘缓存装饰器 — 安全加固版。

变更摘要：
- MD5 → SHA256（抗碰撞）
- pickle.load 前使用 HMAC-SHA256 签名验证数据完整性
- 签名密钥来源于机器级随机字节，首次运行时生成并存储
"""

import hashlib
import hmac
import os
import pickle
import secrets
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_HMAC_KEY_FILE = ".cache_hmac_key"


def _get_hmac_key(cache_dir: Path) -> bytes:
    """获取或生成 HMAC 签名密钥。"""
    key_path = cache_dir / _HMAC_KEY_FILE
    if key_path.exists():
        return key_path.read_bytes()
    key = secrets.token_bytes(32)
    cache_dir.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)
    return key


def _sign_data(data: bytes, key: bytes) -> bytes:
    """使用 HMAC-SHA256 对数据签名。"""
    return hmac.new(key, data, hashlib.sha256).digest()


def _verify_data(data: bytes, signature: bytes, key: bytes) -> bool:
    """验证 HMAC-SHA256 签名。"""
    expected = hmac.new(key, data, hashlib.sha256).digest()
    return hmac.compare_digest(expected, signature)


def memoize_to_disk(cache_dir: str | Path = ".cache", depends_on_file_arg: str | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    A secure disk cache using pickle with HMAC signature verification.

    `depends_on_file_arg` is the name of the kwarg (or arg if mapped) that represents a file path
    (e.g., db_path) whose modification time will be included in the cache key.
    """
    cache_path = Path(cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args: Any, **kwargs: Any) -> T:
            # Create a base key using func name, args, kwargs
            key_data = [func.__name__, args, kwargs]

            # If there's a file dependency, include its mtime in the key
            if depends_on_file_arg:
                file_path = kwargs.get(depends_on_file_arg)
                if file_path is None and args:
                    # heuristic: just assume it's the first arg for simplicity if not in kwargs
                    file_path = args[0]

                if file_path and Path(file_path).exists():
                    mtime = os.path.getmtime(file_path)
                    key_data.append(mtime)

            key_hash = hashlib.sha256(pickle.dumps(key_data)).hexdigest()
            cache_file = cache_path / f"{func.__name__}_{key_hash}.pkl"
            sig_file = cache_path / f"{func.__name__}_{key_hash}.sig"

            if cache_file.exists() and sig_file.exists():
                try:
                    raw_data = cache_file.read_bytes()
                    signature = sig_file.read_bytes()
                    hmac_key = _get_hmac_key(cache_path)
                    if _verify_data(raw_data, signature, hmac_key):
                        return pickle.loads(raw_data)
                except Exception:
                    pass  # Fall back to computing if load/verify fails

            result = func(*args, **kwargs)

            try:
                raw_data = pickle.dumps(result)
                hmac_key = _get_hmac_key(cache_path)
                signature = _sign_data(raw_data, hmac_key)
                cache_file.write_bytes(raw_data)
                sig_file.write_bytes(signature)
            except Exception:
                pass  # Just skip caching if we can't write

            return result
        return wrapper
    return decorator
