import hashlib
import os
import pickle
from pathlib import Path
from typing import Any, Callable, TypeVar

T = TypeVar("T")

def memoize_to_disk(cache_dir: str | Path = ".cache", depends_on_file_arg: str | None = None) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    A simple disk cache using pickle.
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

            key_hash = hashlib.md5(pickle.dumps(key_data)).hexdigest()
            cache_file = cache_path / f"{func.__name__}_{key_hash}.pkl"

            if cache_file.exists():
                try:
                    with cache_file.open("rb") as f:
                        return pickle.load(f)
                except Exception:
                    pass  # Fall back to computing if load fails

            result = func(*args, **kwargs)
            
            try:
                with cache_file.open("wb") as f:
                    pickle.dump(result, f)
            except Exception:
                pass  # Just skip caching if we can't write
                
            return result
        return wrapper
    return decorator
