# Metrics (Prometheus + Grafana)

Dragonwilds has no RCON, query port or HTTP API, so metrics come from two places:

- **cAdvisor** (already running in the metrics stack): CPU, memory and network of the
  game container, labelled `server="Dragonwilds"` by a relabel rule on the container UUID.
- **`dragonwilds_exporter.py`**: a stdlib-only Python exporter on port 9881 that reads the
  server log and the save folder, both mounted read-only.

| File | Goes to (on Tower) |
|---|---|
| `dragonwilds_exporter.py` | `metrics/exporter/` |
| `docker-compose.snippet.yml` | a service in `metrics/docker-compose.yml` |
| `prometheus.snippet.yml` | `metrics/prometheus/prometheus.yml` |
| `dragonwilds.json` | `metrics/grafana/dashboards/Dragonwilds/` (Grafana UID `dragonwilds`, path `/d/dragonwilds/dragonwilds-server`) |

Start only the exporter with `docker compose up -d --no-deps dragonwilds-exporter`, then
reload Prometheus with `docker kill -s HUP palworld_metrics-prometheus-1`.

## Privacy

The server log contains the owner's and every player's EOS ID, character name and IP
address. The exporter only exports counts, timestamps and the version string. It never
exports log text, IDs, names or addresses as labels. Addresses are held in memory only to
pair a join with its disconnect. Don't paste raw log lines anywhere public.

## Metrics

| Metric | Source |
|---|---|
| `dragonwilds_up` | 1 when the current log has `CREATE SESSION - Advertise`, no `LogExit`/`RequestExit`, and was written in the last 150 s (the server logs an EOS `HeartbeatSession` every 30 s) |
| `dragonwilds_log_age_seconds`, `dragonwilds_log_readable` | log file mtime |
| `dragonwilds_session_advertised`, `dragonwilds_exiting` | lifecycle lines in the log |
| `dragonwilds_start_timestamp_seconds` | first timestamp in the current log (UTC) |
| `dragonwilds_build_info{version}` | `LogNetVersion: Set ProjectVersion to 1.0.2.2` |
| `dragonwilds_players_online` | joins minus disconnects of joined connections (see below) |
| `dragonwilds_joins_total`, `dragonwilds_leaves_total` | counters, reset at server start |
| `dragonwilds_world_saves_total`, `dragonwilds_last_save_log_timestamp_seconds` | `Save completed SUCCESSFULLY` lines |
| `dragonwilds_save_age_seconds`, `dragonwilds_save_timestamp_seconds`, `dragonwilds_save_bytes`, `dragonwilds_save_files` | newest `SaveGames/*.sav` |

Wings' `states.json` is mode 600 root, so the exporter (uid 65534) cannot read it. "Up"
comes from the log instead. The log and save files are 644 and their directories 755, so
uid 65534 can read them.

The server starts a fresh `RSDragonwilds.log` on every start and renames the old one to
`RSDragonwilds-backup-<date>.log`. The exporter notices the new inode and resets its counters.

## Log patterns (from real logs, server 1.0.2.2, 2026-11-22)

Player names, IDs and IPs are shown as `<name>`, `<id>`, `<ip>`.

Join (one player, Direct connect):
```
LogNet: AddClientConnection: Added client connection: [UNetConnection] RemoteAddr: <ip>:<port>, Name: ..., Driver: ...
LogNet: Login request: ?p=?pf=PC?cpx=1?Name=<name> userId: RedpointEOS:<id> platform: RedpointEOS
LogDomGameMode: Requested unpausing as we have at least one player
LogNet: Join request: /Game/Maps/Server/L_ServerStartup?p=?pf=PC?cpx=1?Name=<name>
LogNet: Join succeeded: <name>
```

The exporter counts `LogNet: Join succeeded: ` as a join, and pairs it with the oldest
`AddClientConnection` address that has not joined yet.

Leave: **NOT VERIFIED yet.** The first player was still connected when this was written
(no disconnect line in 13 minutes of play). The exporter currently uses two candidate
patterns that have not been seen in a Dragonwilds log:

- `UNetConnection::Close: [UNetConnection] RemoteAddr: <ip>:<port>, ...` (standard UE5;
  a leave is counted only when that address had joined)
- `LogDomGameMode: Requested pausing ...` (assumed counterpart of the verified
  `Requested unpausing as we have at least one player`; resets the count to 0)

If neither appears when a player leaves, `dragonwilds_players_online` stays at the last
join count until the server restarts. After the first real disconnect, check with (masking
IDs, names and IPs):

```sh
L=/mnt/cache/appdata/pterodactyl/wings/lib/volumes/0c921bcf-782b-495d-bf5b-bcc0d50a6d91/RSDragonwilds/Saved/Logs/RSDragonwilds.log
grep -nE 'UNetConnection::Close|Close:|CleanUp|pausing|Logout|PostLogin|Unregister|closed|Disconnect' "$L" \
  | grep -vE 'LogConfig|LogIris' \
  | sed -E 's/(RemoteAddr|Name|Driver|Player|UniqueId)(: |=|\[)[^],]*/\1\2<v>/g; s/[0-9A-Fa-f]{32}/<id>/g; s/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+/<ip>/g'
```

Then adjust `CLOSED` / `NO_PLAYERS` in `dragonwilds_exporter.py` and record the real lines here.
