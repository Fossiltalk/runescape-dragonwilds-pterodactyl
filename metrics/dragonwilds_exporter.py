"""Prometheus exporter for a RuneScape: Dragonwilds dedicated server. Stdlib only.

The game has no API (no RCON, no query port), so everything comes from files:
  - the current server log  <volume>/RSDragonwilds/Saved/Logs/RSDragonwilds.log
  - the world saves         <volume>/RSDragonwilds/Saved/SaveGames/*.sav

PRIVACY: the log contains the owner's and players' EOS IDs, names and IPs.
This exporter only ever emits counts, timestamps and the version string.
No log text, ID, name or address is exported or printed.

Config via env:
  DW_SERVER         server label (default Dragonwilds)
  DW_LOG_DIR        dir holding RSDragonwilds.log (default /logs)
  DW_SAVE_DIR       dir holding *.sav (default /saves)
  DW_UP_MAX_AGE     seconds since last log write to still count as up (default 150;
                    the server writes an EOS HeartbeatSession line every 30 s)
  LISTEN_PORT       default 9881
"""
import calendar, glob, os, re, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVER = os.environ.get("DW_SERVER", "Dragonwilds")
LOG = os.path.join(os.environ.get("DW_LOG_DIR", "/logs"), "RSDragonwilds.log")
SAVES = os.environ.get("DW_SAVE_DIR", "/saves")
UP_MAX_AGE = float(os.environ.get("DW_UP_MAX_AGE", "150"))
PORT = int(os.environ.get("LISTEN_PORT", "9881"))

TS = re.compile(r"^\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})\]")
VERSION = re.compile(r"LogNetVersion: Set ProjectVersion to ([0-9][0-9.]*[0-9])")
ADVERTISED = "LogDomMatcherSession: CREATE SESSION - Advertise"
EXITING = re.compile(r"LogExit: Exiting|RequestExit\(")
SAVED = "Save completed SUCCESSFULLY"
# Connection lifecycle (verified against real logs 2026-11-22, see metrics/README.md).
# Addresses are only used as in-memory keys to pair joins with closes.
ADD_CONN = re.compile(r"LogNet: AddClientConnection: .*RemoteAddr: (\S+?),")
JOINED = "LogNet: Join succeeded: "
CLOSED = re.compile(r"UNetConnection::Close: .*RemoteAddr: (\S+?),")
NO_PLAYERS = "LogDomGameMode: Requested pausing"


def esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def ts(line):
    m = TS.match(line)
    if not m:
        return None
    y, mo, d, h, mi, s, ms = map(int, m.groups())
    return calendar.timegm((y, mo, d, h, mi, s)) + ms / 1000.0  # log stamps are UTC


class LogState:
    """Incrementally follows RSDragonwilds.log; resets when the file is rotated."""

    def __init__(self):
        self.reset(None)

    def reset(self, ino):
        self.ino, self.off, self.buf = ino, 0, b""
        self.version = None
        self.start_ts = None
        self.advertised = 0
        self.exited = 0
        self.last_save_ts = None
        self.saves = 0
        self.joins = 0
        self.leaves = 0
        self.pending = []      # addrs connected but not yet joined (FIFO)
        self.joined = set()    # addrs currently joined

    def feed(self, line):
        t = ts(line)
        if t and self.start_ts is None:
            self.start_ts = t
        if self.version is None:
            m = VERSION.search(line)
            if m:
                self.version = m.group(1)
        if ADVERTISED in line:
            self.advertised = 1
        elif EXITING.search(line):
            self.exited = 1
        elif SAVED in line:
            self.saves += 1
            self.last_save_ts = t or self.last_save_ts
        elif JOINED in line:
            self.joins += 1
            if self.pending:
                self.joined.add(self.pending.pop(0))
        elif NO_PLAYERS in line:
            self.pending.clear(); self.joined.clear()
        else:
            m = ADD_CONN.search(line)
            if m:
                self.pending.append(m.group(1)); return
            m = CLOSED.search(line)
            if m:
                a = m.group(1)
                if a in self.joined:
                    self.joined.discard(a); self.leaves += 1
                elif a in self.pending:
                    self.pending.remove(a)

    def update(self):
        st = os.stat(LOG)
        if st.st_ino != self.ino or st.st_size < self.off:
            self.reset(st.st_ino)
        if st.st_size > self.off:
            with open(LOG, "rb") as f:
                f.seek(self.off)
                data = self.buf + f.read()
                self.off = f.tell()
            *lines, self.buf = data.split(b"\n")
            for raw in lines:
                self.feed(raw.decode("utf-8", "replace"))
        return st.st_mtime


STATE = LogState()
LOCK = threading.Lock()


def collect():
    out, seen = [], set()

    def emit(name, help_, value, typ="gauge", **extra):
        if name not in seen:
            out.append(f"# HELP {name} {help_}\n# TYPE {name} {typ}")
            seen.add(name)
        lab = ",".join(f'{k}="{esc(v)}"' for k, v in {"server": SERVER, **extra}.items())
        out.append(f"{name}{{{lab}}} {value}")

    now = time.time()
    with LOCK:
        try:
            mtime = STATE.update()
            log_ok = 1
        except Exception:
            mtime, log_ok = None, 0
        return render(emit, out, now, mtime, log_ok)


def render(emit, out, now, mtime, log_ok):
    s = STATE
    up = int(bool(log_ok and s.advertised and not s.exited and now - mtime <= UP_MAX_AGE))
    emit("dragonwilds_up", "1 if the session is advertised, not exiting, and the log was written recently", up)
    emit("dragonwilds_log_readable", "1 if RSDragonwilds.log could be read", log_ok)
    if mtime is not None:
        emit("dragonwilds_log_age_seconds", "Seconds since RSDragonwilds.log was last written", round(now - mtime, 1))
        emit("dragonwilds_session_advertised", "1 once CREATE SESSION - Advertise appeared in the current log", s.advertised)
        emit("dragonwilds_exiting", "1 once LogExit/RequestExit appeared in the current log", s.exited)
        if s.start_ts:
            emit("dragonwilds_start_timestamp_seconds", "Time of the first line of the current log (server start)", round(s.start_ts, 3))
        if s.version:
            emit("dragonwilds_build_info", "Server ProjectVersion from the log", 1, version=s.version)
        emit("dragonwilds_players_online", "Players joined and not yet disconnected (from the log)", len(s.joined))
        emit("dragonwilds_joins_total", "Join succeeded lines since server start", s.joins, "counter")
        emit("dragonwilds_leaves_total", "Disconnects of joined players since server start", s.leaves, "counter")
        emit("dragonwilds_world_saves_total", "Save completed SUCCESSFULLY lines since server start", s.saves, "counter")
        if s.last_save_ts:
            emit("dragonwilds_last_save_log_timestamp_seconds", "Time of the last successful save in the log", round(s.last_save_ts, 3))
    savs = []
    for p in glob.glob(os.path.join(SAVES, "*.sav")):
        try:
            savs.append(os.stat(p))
        except OSError:
            pass
    emit("dragonwilds_save_files", "Number of .sav files in SaveGames", len(savs))
    if savs:
        newest = max(savs, key=lambda x: x.st_mtime)
        emit("dragonwilds_save_age_seconds", "Seconds since the newest .sav was modified", round(now - newest.st_mtime, 1))
        emit("dragonwilds_save_timestamp_seconds", "mtime of the newest .sav", round(newest.st_mtime, 3))
        emit("dragonwilds_save_bytes", "Size of the newest .sav", newest.st_size)
    return "\n".join(out) + "\n"


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") not in ("/metrics", ""):
            self.send_response(404); self.end_headers(); return
        body = collect().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
