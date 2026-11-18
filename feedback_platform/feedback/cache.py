import logging
import uuid

from django.core.cache import cache

logger = logging.getLogger(__name__)

ANALYTICS_CACHE_TTL = 60          # Fresh TTL (seconds)
ANALYTICS_STALE_TTL = 300         # Stale-while-revalidate fallback TTL (seconds)
ANALYTICS_LOCK_TTL = 5            # Single-flight lock TTL (seconds)
ANALYTICS_VERSION_TTL = 86400     # Version key retention (24 hours)


def _org_version_key(org_id) -> str:
    return f"analytics_ver:org:{org_id}"


def _branch_version_key(branch_id) -> str:
    return f"analytics_ver:branch:{branch_id}"


def _bump_version_key(key: str) -> None:
    """
    Atomically increment a cache version counter, initializing it if absent.
    Safe across both RedisCache (atomic INCR) and LocMemCache.
    """
    try:
        cache.incr(key)
    except ValueError:
        # Key does not exist yet; initialize to 2 (so it differs from default 1).
        if not cache.add(key, 2, timeout=ANALYTICS_VERSION_TTL):
            try:
                cache.incr(key)
            except Exception:
                cache.set(key, uuid.uuid4().hex[:12], timeout=ANALYTICS_VERSION_TTL)
    except Exception as exc:
        logger.warning("Failed to bump analytics cache version key %s: %s", key, exc)


def bump_analytics_cache_version(org_id, branch_id=None) -> None:
    """
    Version-bump the analytics cache keys for the organization and branch.
    Intended to be invoked inside `transaction.on_commit(...)` after new feedback commits.
    """
    if org_id:
        _bump_version_key(_org_version_key(org_id))
    if branch_id:
        _bump_version_key(_branch_version_key(branch_id))


def get_analytics_cache_version(org_id, target_branch_ids) -> str:
    """
    Returns the active version token for the queried scope.
    - Single-branch queries scope to that branch's version key (avoiding cross-branch churn).
    - Multi-branch / org-wide queries scope to the organization's version key.
    """
    try:
        if len(target_branch_ids) == 1:
            key = _branch_version_key(target_branch_ids[0])
        else:
            key = _org_version_key(org_id)

        version = cache.get(key)
        if version is None:
            cache.add(key, 1, timeout=ANALYTICS_VERSION_TTL)
            version = cache.get(key) or 1
        return str(version)
    except Exception as exc:
        logger.warning("Failed to read analytics cache version: %s", exc)
        return "0"


def build_analytics_cache_key(org_id, target_branch_ids, start_date_str: str, end_date_str: str) -> str:
    version = get_analytics_cache_version(org_id, target_branch_ids)
    branch_ids_key = "_".join(sorted(str(b) for b in target_branch_ids))
    return f"analytics:v{version}:{org_id}:{branch_ids_key}:{start_date_str}:{end_date_str}"
