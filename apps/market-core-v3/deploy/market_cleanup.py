#!/usr/bin/env python3
"""Capture active source and reversibly retire the old market GUI services.

Linux VPS srv1913330 only. Python 3.8+, standard library only.

  sudo python3 market_cleanup.py prepare
  sudo python3 market_cleanup.py stop-old
  sudo python3 market_cleanup.py restore /home/bankadmin/market-cleanup-.../restore.json

prepare: source ZIP + current service plan; no service changes.
stop-old: prepare first, then stop/disable the exact old units embedded below.
         ALL CURRENT MARKET GUIS AND THEIR LIVE ANALYTICS GO OFFLINE.
         The replacement cores/GUI are not installed by this tool.
restore: re-enable and restart units that were enabled/running before cleanup.

Never deletes, moves, or edits installed code, unit files, databases or data.
Keeps collectors, collector cron jobs, FYERS auth/bot, Codex worker, nginx, SSH,
systemd user managers and research evidence files. Retires old GUI alert jobs,
GUI rollover timers and the old nightly/sample-generation jobs as listed.

The shareable ZIP contains selected project code, restricted config copies and
source metadata. Environment/credential files, large data, databases and venv
dependencies are excluded. Known embedded credential patterns cause a source
file to be omitted, not rewritten. Review the ZIP before uploading it.

No network calls; no application code imports/execution; no blanket pkill/kill.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import socket
import stat
import subprocess
import sys
import zipfile


EXPECTED_HOST = "srv1913330"
OWNER = "bankadmin"
USER_MANAGER = "codexuser"
TARGETS = [{'scope': 'system', 'name': 'banknifty-live-dashboard.service', 'workdir': '/opt/banknifty-live-dashboard', 'fragment': '/etc/systemd/system/banknifty-live-dashboard.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-gui.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.58-continuous-replay-cash-vix', 'fragment': '/etc/systemd/system/banknifty-new-divergence-gui.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-live-rollover.service', 'workdir': '', 'fragment': '/etc/systemd/system/banknifty-new-divergence-live-rollover.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-live-rollover.timer', 'workdir': '', 'fragment': '/etc/systemd/system/banknifty-new-divergence-live-rollover.timer'}, {'scope': 'system', 'name': 'banknifty-new-divergence-live.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.32', 'fragment': '/etc/systemd/system/banknifty-new-divergence-live.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-nightly.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.12', 'fragment': '/etc/systemd/system/banknifty-new-divergence-nightly.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-nightly.timer', 'workdir': '', 'fragment': '/etc/systemd/system/banknifty-new-divergence-nightly.timer'}, {'scope': 'system', 'name': 'banknifty-new-divergence-replay-v1047.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.47-replay-correlation-cursor', 'fragment': '/etc/systemd/system/banknifty-new-divergence-replay-v1047.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-replay-v1055.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.55-replay-autopause-fix', 'fragment': '/etc/systemd/system/banknifty-new-divergence-replay-v1055.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-replay-v1056.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.56-cash-breadth-ribbon', 'fragment': '/etc/systemd/system/banknifty-new-divergence-replay-v1056.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-samples.service', 'workdir': '/opt/banknifty-collector', 'fragment': '/etc/systemd/system/banknifty-new-divergence-samples.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-samples.timer', 'workdir': '', 'fragment': '/etc/systemd/system/banknifty-new-divergence-samples.timer'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1035-staging.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.35', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1035-staging.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1039-paper.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.39-paper', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1039-paper.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1040-paper.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.40-paper', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1040-paper.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1042-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.42-alerts', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1042-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1043-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.43-atm-bars', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1043-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1044-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.44-atm-separated', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1044-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1045-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.45-tagged-transitions', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1045-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1046-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.46-correlation-cursor', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1046-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1047-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.47-replay-correlation-cursor', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1047-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1048-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.48-synchronized-option-lanes', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1048-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1049-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.49-completed-minute-synchronization', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1049-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1049-rollover.service', 'workdir': '', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1049-rollover.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1049-rollover.timer', 'workdir': '', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1049-rollover.timer'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1050-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.50-fixed-top-visible-inventory', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1050-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1051-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.51-0945-participation-start', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1051-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1052-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.52-responsive-price-canvas', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1052-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1053-alerts.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.53-aggressive-control-predictions', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1053-alerts.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1053-rollover.service', 'workdir': '', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1053-rollover.service'}, {'scope': 'system', 'name': 'banknifty-new-divergence-v1053-rollover.timer', 'workdir': '', 'fragment': '/etc/systemd/system/banknifty-new-divergence-v1053-rollover.timer'}, {'scope': 'system', 'name': 'banknifty-v2-alerts.service', 'workdir': '/opt/banknifty-v2-gui', 'fragment': '/etc/systemd/system/banknifty-v2-alerts.service'}, {'scope': 'system', 'name': 'banknifty-v2-gui.service', 'workdir': '/opt/banknifty-v2-gui', 'fragment': '/etc/systemd/system/banknifty-v2-gui.service'}, {'scope': 'system', 'name': 'banknifty-v200-live.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-v2.0.0-independent', 'fragment': '/etc/systemd/system/banknifty-v200-live.service'}, {'scope': 'system', 'name': 'banknifty-v200-replay.service', 'workdir': '/home/bankadmin/divergence/releases/banknifty-v2.0.0-independent', 'fragment': '/etc/systemd/system/banknifty-v200-replay.service'}, {'scope': 'system', 'name': 'banknifty-v3-dashboard.service', 'workdir': '/opt/banknifty-v3/app', 'fragment': '/etc/systemd/system/banknifty-v3-dashboard.service'}, {'scope': 'system', 'name': 'banknifty-v5-crowd.service', 'workdir': '/opt/banknifty-v5-crowd', 'fragment': '/etc/systemd/system/banknifty-v5-crowd.service'}, {'scope': 'user:codexuser', 'name': 'banknifty-inventory-horizon-replay.service', 'workdir': '/opt/banknifty/research/vpoc_oi_price_response_v2/inventory_horizon_revision_1', 'fragment': '/home/codexuser/.config/systemd/user/banknifty-inventory-horizon-replay.service'}, {'scope': 'user:codexuser', 'name': 'banknifty-live-market-profiler-v1.service', 'workdir': '/opt/banknifty/research/vpoc_oi_price_response_v2/live_market_profiler_v1', 'fragment': '/home/codexuser/.config/systemd/user/banknifty-live-market-profiler-v1.service'}, {'scope': 'user:codexuser', 'name': 'banknifty-v200-study-gui.service', 'workdir': '/home/codexuser/banknifty-v2.0.0-experimental-study', 'fragment': '/home/codexuser/.config/systemd/user/banknifty-v200-study-gui.service'}, {'scope': 'user:codexuser', 'name': 'nifty-v1062-live.service', 'workdir': '/home/codexuser/nifty-upgrade-bundle-v1062-v200/nifty-v1.0.62', 'fragment': '/home/codexuser/.config/systemd/user/nifty-v1062-live.service'}, {'scope': 'user:codexuser', 'name': 'nifty-v1062-replay.service', 'workdir': '/home/codexuser/nifty-upgrade-bundle-v1062-v200/nifty-v1.0.62', 'fragment': '/home/codexuser/.config/systemd/user/nifty-v1062-replay.service'}, {'scope': 'user:codexuser', 'name': 'nifty-v1062-rollover.service', 'workdir': '!/home/codexuser', 'fragment': '/home/codexuser/.config/systemd/user/nifty-v1062-rollover.service'}, {'scope': 'user:codexuser', 'name': 'nifty-v1062-rollover.timer', 'workdir': '', 'fragment': '/home/codexuser/.config/systemd/user/nifty-v1062-rollover.timer'}, {'scope': 'user:codexuser', 'name': 'nifty-v200-live.service', 'workdir': '/home/codexuser/nifty-upgrade-bundle-v1062-v200/nifty-v2.0.0-independent', 'fragment': '/home/codexuser/.config/systemd/user/nifty-v200-live.service'}, {'scope': 'user:codexuser', 'name': 'nifty-v200-replay.service', 'workdir': '/home/codexuser/nifty-upgrade-bundle-v1062-v200/nifty-v2.0.0-independent', 'fragment': '/home/codexuser/.config/systemd/user/nifty-v200-replay.service'}]  # Fixed list from the supplied inventory.
PROJECTS = {
    "banknifty-live-v1053": "/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.53-aggressive-control-predictions",
    "banknifty-v1062": "/home/bankadmin/divergence/releases/banknifty-new-divergence-v1.0.62-sequence-audit",
    "banknifty-v200": "/home/bankadmin/divergence/releases/banknifty-v2.0.0-independent",
    "nifty-v1062": "/home/codexuser/nifty-upgrade-bundle-v1062-v200/nifty-v1.0.62",
    "nifty-v200": "/home/codexuser/nifty-upgrade-bundle-v1062-v200/nifty-v2.0.0-independent",
}
STARTER = Path("/home/codexuser/nifty-upgrade-bundle-v1062-v200/start_v1_live_user.py")
SKIP_DIRS = {"data", "gui_data", "state", "states", "sessions", "raw", "oi", "minute", "logs", "log", "backups", "backup", "audit", "reports", "results", "evidence", "datasets", "fixtures", "node_modules", "venv", "env", "__pycache__", "dist", "build"}
EXTENSIONS = {".py", ".sh", ".js", ".jsx", ".ts", ".tsx", ".html", ".css", ".toml", ".cfg", ".ini", ".md", ".service", ".timer"}
JSON_NAMES = {"live_config.json", "replay_config.json", "user_live_config.json", "user_replay_config.json", "engine_config.json", "package.json"}
SENSITIVE = re.compile(r"password|passwd|secret|credential|api.?key|access.?token|refresh.?token|bot.?token|authorization|cookie|private.?key|client.?id|chat.?id", re.I)
CREDENTIAL_NAME = re.compile(r"(?:^|[_.-])(?:env|secrets?|credentials?|tokens?|passwords?|id_rsa|id_ed25519)(?:$|[_.-])", re.I)
LITERAL_SECRET = re.compile(r'''(?ix)\b(?:api_?key|access_?token|refresh_?token|bot_?token|password|passwd|client_?secret)\b["']?\s*[:=]\s*["']([^"'\r\n]{8,})["']''')
KNOWN_SECRET = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}|https?://[^/\s:@]+:[^/\s@]+@")
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 30 * 1024 * 1024
FIELDS = "Id,LoadState,ActiveState,SubState,UnitFileState,FragmentPath,WorkingDirectory,MainPID,ControlGroup"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def run(argv):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=90, check=False, env=dict(os.environ, LC_ALL="C", SYSTEMD_PAGER="cat", SYSTEMD_COLORS="0"))
    if result.returncode:
        raise RuntimeError("Command failed (exit %s): %s" % (result.returncode, shlex.join(argv)))
    return result.stdout.decode("utf-8", "replace")


def prefix(scope):
    if scope == "system":
        return ["systemctl"]
    if scope != "user:" + USER_MANAGER:
        raise RuntimeError("Unrecognized service scope")
    account = pwd.getpwnam(USER_MANAGER)
    runtime = "/run/user/" + str(account.pw_uid)
    if not Path(runtime, "bus").exists():
        raise RuntimeError("The existing codexuser service manager is unavailable; no user manager will be started by this tool.")
    return ["runuser", "-u", USER_MANAGER, "--", "env", "XDG_RUNTIME_DIR=" + runtime, "DBUS_SESSION_BUS_ADDRESS=unix:path=" + runtime + "/bus", "systemctl", "--user"]


def inspect(target):
    raw = run(prefix(target["scope"]) + ["show", "--no-pager", "--property=" + FIELDS, target["name"]])
    fields = dict(line.split("=", 1) for line in raw.splitlines() if "=" in line)
    if fields.get("LoadState") != "loaded" or fields.get("Id") != target["name"]:
        raise RuntimeError("Service unavailable or renamed: " + target["name"])
    if fields.get("FragmentPath", "") != target["fragment"] or fields.get("WorkingDirectory", "") != target["workdir"]:
        raise RuntimeError("Service definition location/working directory changed since the inventory: " + target["name"])
    if fields.get("ActiveState") not in {"active", "inactive", "failed"}:
        raise RuntimeError("Service is changing state; retry later: " + target["name"])
    if fields.get("UnitFileState") not in {"enabled", "enabled-runtime", "disabled", "static"}:
        raise RuntimeError("Unexpected enablement state: " + target["name"])
    return dict(target, before=fields)


def private_write(path, data, account):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        os.fchown(handle.fileno(), account.pw_uid, account.pw_gid)
        handle.write(data)


def scrub_config(value, key=""):
    if SENSITIVE.search(key):
        return "<REDACTED>"
    if isinstance(value, dict):
        return {k: scrub_config(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [scrub_config(v, key) for v in value]
    if isinstance(value, str) and KNOWN_SECRET.search(value):
        return "<REDACTED>"
    return value


def embedded_secret(text):
    if KNOWN_SECRET.search(text):
        return True
    for match in LITERAL_SECRET.finditer(text):
        value = match.group(1)
        if value.startswith(("/", "./", "../", "${", "$", "<")):
            continue
        return True
    return False


def allowed(path):
    name = path.name
    if name.startswith(".") or CREDENTIAL_NAME.search(name):
        return False
    if path.suffix.lower() in EXTENSIONS or name in JSON_NAMES:
        return True
    return name.startswith("requirements") and name.endswith(".txt")


def read_regular(path):
    if path.is_symlink():
        raise ValueError("symlink excluded")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as handle:
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE:
            raise ValueError("nonregular or oversized file excluded")
        data = handle.read(MAX_FILE + 1)
        after = os.fstat(handle.fileno())
    if len(data) > MAX_FILE or (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError("file changed during collection or exceeds size limit")
    return data


def add_source(archive, path, member, manifest, force=False):
    if not force and not allowed(path):
        return
    try:
        data = read_regular(path)
        text = data.decode("utf-8")
        original_hash = hashlib.sha256(data).hexdigest()
        changed = False
        if path.name in JSON_NAMES:
            obj = json.loads(text)
            cleaned = scrub_config(obj)
            changed = cleaned != obj
            if changed:
                data = (json.dumps(cleaned, indent=2) + "\n").encode()
            if embedded_secret(data.decode()):
                raise ValueError("possible embedded credential; file omitted")
        elif embedded_secret(text):
            raise ValueError("possible embedded credential; file omitted")
        if manifest["total_bytes"] + len(data) > MAX_TOTAL:
            raise RuntimeError("Source collection exceeds 30 MiB; stopped without changing services")
        archive.writestr(member, data)
        manifest["total_bytes"] += len(data)
        manifest["files"].append({"source": str(path), "archive_path": member, "original_sha256": original_hash, "archived_sha256": hashlib.sha256(data).hexdigest(), "config_redacted": changed, "bytes": len(data)})
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        manifest["omitted"].append({"source": str(path), "reason": str(exc) if isinstance(exc, ValueError) and not isinstance(exc, (UnicodeError, json.JSONDecodeError)) else type(exc).__name__})


def walk_source(archive, root, label, manifest):
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError("Required source root unavailable or is a symlink: " + str(root))
    count = 0
    def onerror(error):
        raise RuntimeError("Cannot read source directory: " + str(error.filename))
    for folder, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith((".", "data-")) and "backup" not in d.lower() and not CREDENTIAL_NAME.search(d) and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            path = Path(folder) / name
            count += 1
            if count > 5000:
                raise RuntimeError("Source tree exceeds 5000 entries: " + str(root))
            add_source(archive, path, label + "/" + path.relative_to(root).as_posix(), manifest)


def capture(output, owner, snapshot):
    manifest = {"created_utc": now(), "hostname": socket.gethostname(), "files": [], "omitted": [], "total_bytes": 0, "installed_package_notes": [], "note": "Only listed project source is copied. Config redactions and omitted files are recorded. Review before sharing; the scan cannot recognize every possible hardcoded secret."}
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        os.fchown(handle.fileno(), owner.pw_uid, owner.pw_gid)
        with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for label, root_text in PROJECTS.items():
                root = Path(root_text)
                print("Capturing " + root_text, flush=True)
                walk_source(archive, root, "projects/" + label, manifest)
                # Copy only our own installed package, never the whole venv.
                # This resolves source-folder vs installed-wheel differences.
                if "v1062" in label or "v1053" in label:
                    package_name = "nifty_profiler" if label.startswith("nifty-") else "banknifty_profiler"
                    distribution_name = package_name.replace("_profiler", "_market_profiler")
                    found = False
                    for site in sorted((root / ".venv/lib").glob("python*/site-packages")):
                        package = site / package_name
                        if package.is_dir() and not package.is_symlink():
                            walk_source(archive, package, "installed/" + label + "/" + site.parent.name + "/" + package_name, manifest)
                            found = True
                        # Read package installer metadata without importing it.
                        metadata_dirs = set(site.glob(package_name + "*.dist-info")) | set(site.glob(distribution_name + "*.dist-info"))
                        for meta in sorted(metadata_dirs):
                            for name in ("METADATA", "entry_points.txt", "direct_url.json"):
                                file = meta / name
                                if file.is_file():
                                    add_source(archive, file, "installed/" + label + "/metadata/" + meta.name + "/" + name, manifest, force=True)
                        editable_files = set(site.glob("__editable__*" + package_name + "*")) | set(site.glob("__editable__*" + distribution_name + "*"))
                        for file in sorted(editable_files):
                            if file.is_file():
                                add_source(archive, file, "installed/" + label + "/editable/" + file.name, manifest, force=True)
                    launcher = root / ".venv/bin/banknifty-new-divergence"
                    if launcher.is_file():
                        add_source(archive, launcher, "installed/" + label + "/entrypoint.py", manifest, force=True)
                    if not found:
                        manifest["installed_package_notes"].append(label + ": no regular installed package directory; source/editable metadata must be checked")
            if not STARTER.is_file():
                raise RuntimeError("Required NIFTY startup wrapper is missing: " + str(STARTER))
            add_source(archive, STARTER, "startup/start_v1_live_user.py", manifest, force=True)
            archive.writestr("source-manifest.json", json.dumps(manifest, indent=2) + "\n")
            archive.writestr("service-plan.json", json.dumps(snapshot, indent=2) + "\n")
            archive.writestr("READ-ME.txt", "Review source-manifest.json and the copied code before uploading.\nThis contains project source, selected installed project modules, restricted config copies and service metadata.\nIt excludes environment files, credentials by filename/known patterns, datasets, databases, dependency environments and backup folders.\nPossible embedded credentials cause an entire source file to be omitted. This detection is not exhaustive.\nNo source files were changed on the VPS.\n")
    return manifest


def state_document(records):
    return {"format_version": 1, "hostname": socket.gethostname(), "created_utc": now(), "records": records}


def validate_saved(saved):
    if saved.get("format_version") != 1 or saved.get("hostname", "").split(".")[0] != EXPECTED_HOST:
        raise RuntimeError("Restore file belongs to a different host or format")
    expected = {(t["scope"], t["name"]): t for t in TARGETS}
    records = saved.get("records", [])
    if len(records) != len(expected):
        raise RuntimeError("Incomplete restore file")
    seen = set()
    for record in records:
        key = (record.get("scope"), record.get("name"))
        if key not in expected or key in seen or any(record.get(k) != v for k, v in expected[key].items()):
            raise RuntimeError("Restore target is not in the fixed cleanup list")
        seen.add(key)
        if record.get("before", {}).get("ActiveState") not in {"active", "inactive", "failed"} or record["before"].get("UnitFileState") not in {"enabled", "enabled-runtime", "disabled", "static"}:
            raise RuntimeError("Invalid restore state")
    return records


def restore(records):
    errors = []
    for record in records:
        before = record["before"]
        if before["UnitFileState"] in {"enabled", "enabled-runtime"}:
            args = ["enable"] + (["--runtime"] if before["UnitFileState"] == "enabled-runtime" else [])
            try:
                run(prefix(record["scope"]) + args + [record["name"]])
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                errors.append(str(exc))
    # Start application services first, then their timers.
    for record in sorted(records, key=lambda r: r["name"].endswith(".timer")):
        if record["before"]["ActiveState"] == "active":
            try:
                run(prefix(record["scope"]) + ["start", record["name"]])
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                errors.append(str(exc))
    return errors


def stop_old(records):
    # Disable and stop timers before the services they can restart.
    for record in sorted(records, key=lambda r: not r["name"].endswith(".timer")):
        command = prefix(record["scope"])
        print("Retiring " + record["scope"] + " " + record["name"], flush=True)
        if record["before"]["UnitFileState"] in {"enabled", "enabled-runtime"}:
            extra = ["--runtime"] if record["before"]["UnitFileState"] == "enabled-runtime" else []
            run(command + ["disable"] + extra + [record["name"]])
        run(command + ["stop", record["name"]])
    after = [inspect(record) for record in TARGETS]
    for record in after:
        state = record["before"]
        if state["ActiveState"] == "active" or state["UnitFileState"] in {"enabled", "enabled-runtime"}:
            raise RuntimeError("Service still running/enabled: " + record["name"])
    return after


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["prepare", "stop-old", "restore"])
    parser.add_argument("restore_file", nargs="?")
    args = parser.parse_args()
    if sys.platform != "linux" or os.geteuid() != 0:
        parser.error("Run with sudo on the Linux VPS.")
    if socket.gethostname().split(".")[0] != EXPECTED_HOST:
        parser.error("Host does not match the uploaded inventory; refusing service changes.")
    owner = pwd.getpwnam(OWNER)
    if args.action == "restore":
        if not args.restore_file:
            parser.error("restore requires the saved restore.json path")
        records = validate_saved(json.loads(read_regular(Path(args.restore_file))))
        # Recheck ownership/location of every unit before any restore write.
        for target in TARGETS:
            inspect(target)
        errors = restore(records)
        if errors:
            raise RuntimeError("Some restore operations failed:\n" + "\n".join(errors))
        for record in records:
            current = inspect(record)["before"]
            if record["before"]["ActiveState"] == "active" and current["ActiveState"] != "active":
                raise RuntimeError("Restore started but unit is not active: " + record["name"])
        print("Previously enabled/running services restored. Check the GUIs for application health.")
        return
    if args.restore_file:
        parser.error("Only restore accepts a restore-file path")
    print("Checking the fixed service list against the current host...", flush=True)
    records = [inspect(target) for target in TARGETS]
    directory = Path(owner.pw_dir) / ("market-cleanup-" + dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M%S-%f"))
    directory.mkdir(mode=0o700)
    os.chown(directory, owner.pw_uid, owner.pw_gid)
    saved = state_document(records)
    source_zip = directory / "market-active-sources.zip"
    manifest = capture(source_zip, owner, saved)
    if not manifest["files"]:
        raise RuntimeError("No source files were captured; no services changed")
    print("Source ZIP: " + str(source_zip))
    if manifest["omitted"]:
        print("Some files were omitted. Review source-manifest.json in the ZIP.")
    script_path = Path(__file__).resolve()
    restore_path = directory / "restore.json"
    private_write(restore_path, (json.dumps(saved, indent=2) + "\n").encode(), owner)
    restore_command = shlex.join(["sudo", "python3", str(script_path), "restore", str(restore_path)])
    private_write(directory / "RESTORE.txt", (restore_command + "\n").encode(), owner)
    if args.action == "prepare":
        print("Preparation complete. No services changed. Review service-plan.json in the ZIP.")
    else:
        # Capturing source can take time. Recheck every target immediately before
        # writes, and refuse if another deployment changed service state.
        fresh = [inspect(target) for target in TARGETS]
        keys = ("ActiveState", "UnitFileState", "MainPID")
        if any(any(a["before"].get(k) != b["before"].get(k) for k in keys) for a, b in zip(records, fresh)):
            raise RuntimeError("Service state changed during source capture. Nothing was stopped; rerun to refresh the snapshot.")
        print("Stopping the old GUIs/analytics and scheduled old replay jobs. Collector and authentication services are excluded.", flush=True)
        try:
            after = stop_old(records)
            private_write(directory / "after.json", (json.dumps(state_document(after), indent=2) + "\n").encode(), owner)
            print("Old target services are stopped and disabled where applicable. Replacement cores/GUI have not been installed.")
        except (Exception, KeyboardInterrupt) as exc:
            print("Cleanup interrupted; attempting to restore previously running services.", flush=True)
            errors = restore(records)
            private_write(directory / "failure.txt", (type(exc).__name__ + ": " + str(exc) + "\n" + "\n".join(errors)).encode(), owner)
            print("Restore command: " + restore_command)
            raise RuntimeError("Cleanup did not complete. Inspect " + str(directory / "failure.txt")) from None
    print("Restore command: " + restore_command)
    print("Download the source ZIP from Windows PowerShell:")
    print("scp " + OWNER + "@200.234.39.232:" + str(source_zip) + ' "$env:USERPROFILE\\Downloads"')
    print("Review and upload market-active-sources.zip. Keep restore.json and RESTORE.txt on the VPS.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))
