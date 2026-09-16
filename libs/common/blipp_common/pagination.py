"""
pagination.py — Feed cursor encoding/decoding.

Two cursor types are supported, distinguished by prefix:
  r:<base64> — Ranked cursor (position in Gorse candidate list)
  c:<base64> — Chronological cursor (created_at + blipp_id)

Use encode_ranked_cursor / decode_ranked_cursor for ranked pages.
Use encode_cursor / decode_cursor for chronological fallback pages.
"""
import base64
from datetime import datetime
from typing import Optional, Tuple, Union


# ── Chronological cursor (legacy, unchanged) ─────────────────────────────────

def encode_cursor(timestamp: datetime, entity_id: str) -> str:
    """Encode a chronological (created_at + blipp_id) cursor."""
    raw = f"c|{timestamp.isoformat()}|{entity_id}"
    return base64.b64encode(raw.encode()).decode()


def decode_cursor(cursor: Optional[str]) -> Optional[Tuple[datetime, str]]:
    """Decode a chronological cursor. Returns None for ranked or invalid cursors."""
    if not cursor:
        return None
    try:
        raw = base64.b64decode(cursor.encode()).decode()
        parts = raw.split("|", 2)
        if len(parts) == 3 and parts[0] == "c":
            # New format: c|timestamp|entity_id
            _, ts_str, entity_id = parts
        elif len(parts) == 2:
            # Legacy format: timestamp|entity_id (no prefix)
            ts_str, entity_id = parts
        else:
            return None
        return datetime.fromisoformat(ts_str), entity_id
    except Exception:
        return None


# ── Ranked cursor (Gorse candidate position) ──────────────────────────────────

def encode_ranked_cursor(position: int, cache_key: str) -> str:
    """
    Encode a ranked feed cursor.
    
    Args:
        position: Index into the Gorse candidate list (0-based position of next item)
        cache_key: Redis key where the candidate list is stored (for validation)
    """
    raw = f"r|{position}|{cache_key}"
    return base64.b64encode(raw.encode()).decode()


def decode_ranked_cursor(cursor: Optional[str]) -> Optional[Tuple[int, str]]:
    """
    Decode a ranked cursor.
    
    Returns:
        (position, cache_key) tuple, or None if not a ranked cursor or invalid.
    """
    if not cursor:
        return None
    try:
        raw = base64.b64decode(cursor.encode()).decode()
        parts = raw.split("|", 2)
        if len(parts) == 3 and parts[0] == "r":
            _, position_str, cache_key = parts
            return int(position_str), cache_key
        return None
    except Exception:
        return None


def cursor_is_ranked(cursor: Optional[str]) -> bool:
    """Returns True if this cursor encodes a ranked position."""
    return decode_ranked_cursor(cursor) is not None
