from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading


def encode(value):
    return json.dumps(value, allow_nan=False, separators=(",", ":")).encode()


def atomic_write(path, body):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class PublishedStore:
    """Cached bytes: readers never call the engine or hold its locks."""
    def __init__(self, config):
        self.config = config
        self.lock = threading.Lock()
        self.current = {}
        self.indicator_current = None
        self.health = {"status": "starting", "instrument": config.instrument}
        self.catalogs = {p: [] for p in (config.profile("v1062"), config.profile("v200"))}
        self.reload_catalogs()

    def reload_catalogs(self):
        for profile in self.catalogs:
            root = self.config.state_root / "replay" / profile
            entries = []
            for meta in sorted(root.glob("*.meta.json")):
                try:
                    row = json.loads(meta.read_text())
                    if row.get("profile") == profile and (root / (row["id"] + ".json.gz")).is_file():
                        entries.append(row)
                except (OSError, ValueError, KeyError):
                    continue
            with self.lock:
                self.catalogs[profile] = sorted(entries, key=lambda r: (r["session"], r["id"]), reverse=True)

    def set_health(self, health):
        with self.lock:
            self.health = dict(health)

    def reset_live(self):
        with self.lock:
            self.current = {}
            self.indicator_current = None

    def publish_indicator_inputs(self, feed):
        body = encode(feed)
        with self.lock:
            self.indicator_current = body

    def indicator_inputs(self):
        with self.lock:
            return self.indicator_current

    def publish(self, profile, payload, *, source="recorded", key=None, live=False):
        self.config.check_profile(profile)
        day = payload["session"]
        key = key or (source + "-" + day)
        if not re.fullmatch(r"[a-z0-9-]{1,90}", key):
            raise ValueError("Invalid replay key")
        body = encode(payload)
        compressed = gzip.compress(body, compresslevel=1, mtime=0)
        etag = '"' + hashlib.sha256(compressed).hexdigest() + '"'
        root = self.config.state_root / "replay" / profile
        row = dict(id=key, profile=profile, session=day, source=source,
            payload="/api/replay?profile=" + profile + "&key=" + key,
            sha256=hashlib.sha256(body).hexdigest())
        atomic_write(root / (key + ".json.gz"), compressed)
        atomic_write(root / (key + ".meta.json"), encode(row))
        with self.lock:
            if live:
                self.current[profile] = (body, compressed, etag)
            rows = [r for r in self.catalogs[profile] if r["id"] != key] + [row]
            self.catalogs[profile] = sorted(rows, key=lambda r: (r["session"], r["id"]), reverse=True)

    def catalog(self, profile):
        self.config.check_profile(profile)
        with self.lock:
            return {"profile": profile, "sessions": list(self.catalogs[profile])}

    def live(self, profile):
        self.config.check_profile(profile)
        with self.lock:
            return self.current.get(profile)

    def replay(self, profile, key):
        self.config.check_profile(profile)
        with self.lock:
            if not any(r["id"] == key for r in self.catalogs[profile]):
                raise FileNotFoundError("Recorded session unavailable")
        if not re.fullmatch(r"[a-z0-9-]{1,90}", key):
            raise ValueError("Invalid replay key")
        return (self.config.state_root / "replay" / profile / (key + ".json.gz")).read_bytes()
