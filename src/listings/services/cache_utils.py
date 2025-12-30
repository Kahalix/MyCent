from django.core.cache import cache
from django.conf import settings
import random
import logging

logger = logging.getLogger(__name__)

# klucz wersji
_CACHE_VERSION_KEY = "public_itemsets:version"
_DEFAULT_VERSION = 1

def get_public_itemsets_cache_version() -> int:
    """
    Bezpiecznie pobiera wersję cache. Jeśli backend cache (Redis) jest niedostępny,
    logujemy debugowo i zwracamy domyślną wersję zamiast podnosić wyjątek.
    """
    try:
        v = cache.get(_CACHE_VERSION_KEY)
    except Exception as e:
        logger.debug("get_public_itemsets_cache_version: cache.get failed, using default version (%s): %s", _DEFAULT_VERSION, e)
        return _DEFAULT_VERSION

    if v is None:
        try:
            # spróbuj ustawić domyślną wersję (add jest bezpieczne jeśli backend to obsługuje)
            cache.add(_CACHE_VERSION_KEY, _DEFAULT_VERSION)
        except Exception:
            # nie krytyczne — backend może nie wspierać add/incr w test environment
            pass
        return _DEFAULT_VERSION

    try:
        return int(v)
    except Exception:
        return _DEFAULT_VERSION

def get_cache_key(prefix: str, request_path: str) -> str:
    """
    prefix: "public_itemsets:list", "public_itemsets:detail", ...
    request_path: request.get_full_path()
    """
    version = get_public_itemsets_cache_version()
    return f"{prefix}:v{version}:{request_path}"

def invalidate_public_itemsets_cache() -> None:
    """
    Bumpuje wersję cache — tania invalidacja wszystkich wpisów.
    Stosuje INCR jeśli dostępne, fallback -> losowa wartość.
    """
    try:
        # Django-redis backend exposes incr
        cache.incr(_CACHE_VERSION_KEY)
    except Exception as e:
        try:
            # fallback: ustaw losową wartość
            newv = random.randint(1, 10 ** 9)
            cache.set(_CACHE_VERSION_KEY, newv)
            logger.debug("invalidate_public_itemsets_cache: set random version %s (err: %s)", newv, e)
        except Exception:
            logger.exception("invalidate_public_itemsets_cache: failed to bump version")
