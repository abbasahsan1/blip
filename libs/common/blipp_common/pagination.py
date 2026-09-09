import base64
from datetime import datetime
from typing import Optional, Tuple


def encode_cursor(timestamp: datetime, entity_id: str) -> str:
    raw = f"{timestamp.isoformat()}|{entity_id}"
    return base64.b64encode(raw.encode()).decode()


def decode_cursor(cursor: Optional[str]) -> Optional[Tuple[datetime, str]]:
    if not cursor:
        return None
    try:
        raw = base64.b64decode(cursor.encode()).decode()
        ts_str, entity_id = raw.split("|", 1)
        return datetime.fromisoformat(ts_str), entity_id
    except Exception:
        return None
