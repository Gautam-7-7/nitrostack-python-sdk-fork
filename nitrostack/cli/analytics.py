import os
import sys
import json
import hashlib
import socket
import threading
import urllib.request
from typing import Dict, Any, Optional

POSTHOG_API_KEY = "phc_OufG1OuiamSbCBMVHfO70IyFWKBzsiaDpOWqcNwtz6G"
POSTHOG_HOST = "https://us.i.posthog.com"

_pending_threads = []

def get_distinct_id() -> str:
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown-host"
    try:
        username = os.getlogin() or os.environ.get("USERNAME") or os.environ.get("USER") or "unknown-user"
    except Exception:
        username = "unknown-user"
    key = f"{hostname}:{username}".encode("utf-8")
    return hashlib.sha256(key).hexdigest()[:16]

def _send_event_sync(event_name: str, properties: Dict[str, Any]):
    if os.environ.get("NITROSTACK_TELEMETRY_DISABLED", "false").lower() == "true":
        return
        
    payload = {
        "api_key": POSTHOG_API_KEY,
        "event": event_name,
        "properties": {
            "distinct_id": get_distinct_id(),
            **properties
        }
    }
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{POSTHOG_HOST}/capture/",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            resp.read()
    except Exception:
        pass

def track_event(event_name: str, properties: Optional[Dict[str, Any]] = None):
    properties = properties or {}
    t = threading.Thread(target=_send_event_sync, args=(event_name, properties))
    t.daemon = True
    t.start()
    _pending_threads.append(t)

def shutdown_analytics():
    for t in list(_pending_threads):
        if t.is_alive():
            t.join(timeout=2.0)
