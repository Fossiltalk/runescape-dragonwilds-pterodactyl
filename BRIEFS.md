# RuneScape: Dragonwilds dedicated server on Tower: subagent briefs

Written 2026-11-22. Owner: Aaron (GitHub `Fossiltalk`). The pattern is the same as the Palworld, V Rising and Skyrim Together servers: Pterodactyl, a Tailscale sidecar with node sharing, and Prometheus with Grafana.

There are four phases. Phase 1 runs first. Phases 2 and 3 can run in parallel once Phase 1 has a running server. Phase 4 is Aaron's in-game test, and Phase 3 needs it to finish its log-based metrics.

| Phase | Agent | Depends on | Output |
|---|---|---|---|
| 1 | Server | Owner ID from Aaron | Egg imported, server installed, starts and stops cleanly |
| 2 | Sidecar | Phase 1 ports (fixed below) | `dragonwilds` tailnet node forwarding UDP 7777 and 8888 |
| 3 | Metrics | Phase 1 container UUID | cAdvisor label, exporter, Grafana dashboard |
| 4 | Aaron | Phases 1 and 2 | In-game Direct connect over Tailscale, then share the node |

---

## Shared context (every agent reads this)

### Access and layout

- **SSH:** `ssh root@tower` over Tailscale SSH. The first connection can print a check-in URL, which Aaron must approve. Stop and ask him.
- **Pterodactyl:** compose project at `/mnt/cache/appdata/pterodactyl`. Panel is v1.15.2 (`pterodactyl-panel-1`) and Wings is v1.13.5 (`pterodactyl-wings-1`).
  - The Wings data root is `/mnt/cache/appdata/pterodactyl/wings/lib`, the same path inside and outside the container.
  - Server volumes live at `lib/volumes/<uuid>`.
  - Game containers run as uid/gid 988 on network `pterodactyl_nw`, gateway `172.30.0.1`.
  - Wings has no registry auth, so every image must be public.
- **Panel scripting:** write a PHP file, `docker cp` it into `pterodactyl-panel-1:/tmp/x.php`, then `docker exec -w /app pterodactyl-panel-1 php artisan tinker /tmp/x.php`.
  - Inline one-liners break on shell quoting, so always use files.
  - Services already used successfully here: `NestCreationService`, `EggImporterService`, `ServerCreationService`, `DaemonPowerRepository`, `DaemonCommandRepository`.
  - The nest author must be a valid email: use `fossiltalk@users.noreply.github.com`.
- **Database:** `pterodactyl-database-1` (MariaDB, database `panel`). The root password is in `$MYSQL_ROOT_PASSWORD` inside that container, so wrap the query in `sh -c 'mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" panel -e "..."'`.
- **Existing game servers (do not touch):**

  | Server | Ports | Container UUID or sidecar |
  |---|---|---|
  | Paland | 8211/8212/25575 | `0f8ce2e2…` |
  | Palapore | 8213/8214/25576 | `6c3773df…` |
  | V Rising | UDP 9876/9877 | wine yolk |
  | Skyrim Together | UDP 10578 | `ba6bbab4…`, sidecar `skyrim-ts` |

- **Free ports:** UDP 7777 and 8888 were checked free on 2026-11-22.
- **Log:** append dated entries to `/mnt/cache/appdata/pterodactyl/AGENT_LOG.md`. Use **VERIFIED:**, **NOT DONE:** and **ISSUE:** lines, matching the existing style.
- **Backups:** before editing any shared file, copy it to `/mnt/user/backups/palworld-migration/<date>-dragonwilds-<what>/`.

### Facts about the game server (researched 2026-11-22)

- **Install:**
  - Dedicated server app **4019830**, free, with anonymous SteamCMD login.
  - Linux is native: `RSDragonwilds/Binaries/Linux/RSDragonwildsServer-Linux-Shipping`, launched as `RSDragonwildsServer.sh`.
  - Size is about 6–8 GB.
  - The latest client/server version on the wiki is 1.0.1.2 (Oct 2026), which fixed Linux servers crashing on teleport.
- **Config:** `RSDragonwilds/Saved/Config/LinuxServer/DedicatedServer.ini`. The section is `[/Script/Dominion.DedicatedServerSettings]` and the keys are:
  - `OwnerId` (required; the server will not start without it)
  - `ServerName`, `DefaultWorldName`, `AdminPassword` (required)
  - `WorldPassword` (optional)
  - `AdministratorList`
  - `ServerGuid` (generated on first run; never overwrite it)
  - The file also has `[SectionsToSave] bCanSaveAllSections=true`.
  - Edits made while the server is running are lost.
- **Saves:** `RSDragonwilds/Saved/SaveGames/*.sav`. On start the server loads the newest `.sav`, or creates a world. Never rename a `.sav`.
- **Ports:** game on UDP 7777 (`-Port=`) and the "world settings beacon" on UDP 8888 (`-BeaconPort=`). Host and container ports must match, or players are kicked to the title screen.
- **Launch args:** `-log -Port=<p> -BeaconPort=<b> -ini:Game:[/Script/Engine.GameSession]:MaxPlayers=<n>`. The hard maximum is 6 players.
- **Joining:**
  - The public Worlds list is advertised through Epic Online Services (EOS) using the server's **public** IP. Tower is behind CGNAT, so the public list **will not work**. Do not try to make it work.
  - The only path is the **Direct** tab of the Worlds screen, using the Tailscale IP.
  - Direct join by LAN IP is documented. Direct join by a Tailscale 100.x IP is **not confirmed** by any source; Phase 4 tests it.
- **Known issues:**
  - Joining password-protected servers is flaky (wiki), so leave `WorldPassword` empty for the first test. Tailscale node sharing is the access control.
  - Jagex's image has open issues: SIGTERM does not reach the game (#26), and there is no final save on shutdown, so up to 5 minutes can be lost (#28). Verify our stop path saves.
- **Resources:** about 2 GB RAM plus 1 GB per player (8 GB for 6). Four cores are recommended. Tower has 12 cores and about 48 GB available.
- **Server API:** none: no RCON, query API or console commands. Metrics must come from cAdvisor and from log parsing.

### Sources

- https://dragonwilds.runescape.wiki/w/Dedicated_Servers/Linux
- https://dragonwilds.runescape.wiki/w/Dedicated_Servers
- https://github.com/pelican-eggs/games-steamcmd/tree/main/runescape_dragonwilds (egg, exported 2026-04-23)
- https://github.com/runescape/rsdw-dedicated (Jagex official, image `ghcr.io/runescape/rsdw-dedicated`, public; has a `-pelican` tag variant)
- https://github.com/indifferentbroccoli/runescape-dragonwilds-server-docker (community; useful for the INI template and shutdown handling)

### Guardrails (apply to every phase)

1. Do not expose ports publicly or set up router forwards. Access is Tailscale only.
2. Do not restart, recreate or reconfigure the Palworld, V Rising or Skyrim servers or their sidecars.
   - Use `docker compose up -d --no-deps <service>` for anything new.
   - Do not change Panel or Wings config (`config.yml`, `.env`). Ask Aaron first if that seems necessary.
3. Never commit, log to chat, or echo passwords or the Owner ID. Egg defaults stay blank or placeholder. Generate secrets on Tower with `openssl rand`, set them through Panel variables, and report only their length.
4. Do not do anything outside this brief that touches Aaron's accounts: Tailscale admin, Steam, Jagex, or GitHub settings beyond the named repo. If a step needs one, stop and report what Aaron must do.
5. Report outcomes exactly. "Started" means Wings reports the state `running` **and** the done string appeared in the console. Paste evidence lines, not summaries.

---

## Phase 1: Server agent (Pterodactyl egg and server)

**Goal:** a Dragonwilds server in the Panel under a new "Dragonwilds" nest. It installs with SteamCMD, starts, and reaches the done string. It stops cleanly and writes a final save, and its Panel variables land in `DedicatedServer.ini`.

**Input required before starting:** Aaron's **Owner ID**, which is his 32-character EOS/Player ID.
- In game it is under Settings, as the Player ID with a copy button. Confirm the exact location against the wiki before asking.
- If you don't have it, do steps 1–4, then stop and ask.
- Never write it into the repo.

### Steps

1. **Repo.** Create the public repo `Fossiltalk/runescape-dragonwilds-pterodactyl`, using `gh` as Aaron's account. Commit `BRIEFS.md` from this folder. Write a `README.md` modeled on `Fossiltalk/skyrim-together-pterodactyl`'s README, covering setup, updates, backups and how friends connect. Add `egg-runescape-dragonwilds.json`, built as follows.
2. **Egg.** Download the pelican-eggs egg (`egg-pterodactyl-runescape-dragonwilds.json`, PTDL_v2) and adapt it:
   - **Docker image:** keep `ghcr.io/ptero-eggs/steamcmd:debian`, which Tower already uses for Palworld (ptero-eggs is the old name of pelican-eggs). Pull it anonymously from Tower to confirm.
   - **Startup:**
     ```
     ./RSDragonwildsServer.sh -log -Port={{SERVER_PORT}} -BeaconPort={{BEACON_PORT}} -ini:Game:[/Script/Engine.GameSession]:MaxPlayers={{MAX_PLAYERS}}
     ```
     If the `.sh` launcher is not in the installed files, use `./RSDragonwilds/Binaries/Linux/RSDragonwildsServer-Linux-Shipping RSDragonwilds …` with the same args. Check which one exists after the install and record the result.
   - **New variable `BEACON_PORT`:** default `8888`, rules `required|integer|between:1024,65535`, user-viewable but not editable. It must equal the server's second allocation.
   - **`ADMIN_PASSWORD` and `WORLD_PASSWORD`:**
     - Make the default blank.
     - Set `ADMIN_PASSWORD` to `required|string|min:12` and `WORLD_PASSWORD` to `nullable|string`.
     - Hide `ADMIN_PASSWORD` from the user view.
   - **`OWNER_ID`:** keep it `required|alpha_num|size:32` with a blank default.
   - **`config.files`:** it must write `OwnerId`, `ServerName`, `DefaultWorldName`, `AdminPassword` and `WorldPassword` into `RSDragonwilds/Saved/Config/LinuxServer/DedicatedServer.ini` under `[/Script/Dominion.DedicatedServerSettings]`. Never write `ServerGuid`.
     - Check that the ini parser copes with a section name containing `/` and `.`. If it does not, fall back to a startup-time `sed`/`awk` merge in the startup line, using `scripts/merge-optionsettings.awk` on Tower as the model. An earlier agent wrote it for the Palworld INI; read it before reusing it.
     - On first install the INI does not exist yet. The install script must seed a minimal INI with `[SectionsToSave]` and the section header, so the parser has something to edit.
   - **Stop command:** `^C` (SIGINT). Check the done string `CREATE SESSION - Advertise` against the real console output in step 7. If it differs, change it to a line that appears once the server is listening.
   - **Install script:** keep the egg's SteamCMD install (`+login anonymous +app_update 4019830 validate`) and end it with `chown -R 988:988 /mnt/server`.
   - **Updates:** keep the egg's `AUTO_UPDATE` variable, but **default it to 0**. A silent update can break version match with friends' clients, so updates are manual (see README).
3. **Nest and egg in the Panel.**
   - Create the nest "Dragonwilds" with `NestCreationService`.
   - Import the egg with `EggImporterService`.
   - Record the nest id and egg id.
4. **Allocations.** Add allocations `0.0.0.0:7777` and `0.0.0.0:8888` on node 1. Check node ids in the Panel database first. Bind to `0.0.0.0` like the other servers; Tower's firewall and CGNAT keep it off the internet, and we add no forwards.
5. **Server.** Create it with `ServerCreationService`:
   - Name "Dragonwilds", owner Aaron's Panel user (look up the id).
   - Primary allocation 7777, extra allocation 8888.
   - 10240 MB RAM, 400% CPU, 20480 MB disk, swap 0.
   - Variables:
     - `SERVER_NAME=Dragonwilds`, `DEFAULT_WORLD_NAME=Tower` (or ask Aaron)
     - `OWNER_ID=<Aaron's>`
     - `ADMIN_PASSWORD=<openssl rand -base64 18>`
     - `WORLD_PASSWORD` blank, `MAX_PLAYERS=6`, `BEACON_PORT=8888`, `AUTO_UPDATE=0`
6. **Install.** Watch it until done. Expect several minutes and about 8 GB downloaded. Confirm the binary exists and the volume belongs to 988:988.
7. **First start.** Start the server with `DaemonPowerRepository`. Then:
   - Tail `wings/lib/volumes/<uuid>`'s logs or the Wings console.
   - Capture the first 40 lines, including the server version line, and the line used as the done string.
   - Confirm Wings `states.json` shows `running`. It flushes about every 60 s, so wait 75 s.
   - Confirm `ss -lun` on Tower shows 7777 and 8888.
   - Confirm `DedicatedServer.ini` has the Panel values. Show the key names and value lengths only. `ServerGuid` should be non-empty.
   - Confirm `SaveGames/` contains a `.sav`.
8. **Clean stop.** Stop the server through the Panel.
   - Confirm the process exits within 30 s, with no crash flag and exit 0 if Wings reports it.
   - Confirm a `.sav` mtime updated at stop. If the server does not save on SIGINT, record it as an **ISSUE**. Then test whether SIGTERM differs (`docker kill -s TERM <uuid>` while running) and choose the stop signal that saves.
9. **Restart check.** Start again, confirm the same world loads (same `.sav` name, `ServerGuid` unchanged), then leave it **running** for Phases 2–4.
10. **Commit** the egg and any scripts to the repo. Append to AGENT_LOG. Report back:
    - The nest, egg and server ids, and the UUID.
    - The allocation ids.
    - The real done string, the launcher used, and the version line.
    - The stop and save result.

**Done when:** steps 6–9 are VERIFIED with evidence, and the repo is pushed with no secrets. Check with `git grep` for the admin password length pattern, and confirm no Owner ID is committed.

---

## Phase 2: Sidecar agent (Tailscale node `dragonwilds`)

**Goal:** a tailnet node `dragonwilds` that DNATs UDP 7777 and 8888 to `172.30.0.1`. This copies the `skyrim` and `vrisingserver` sidecars.

### Steps

1. **Read first.** Read `/mnt/cache/appdata/pterodactyl/sidecars/docker-compose.yml` (project `palworld_sidecars`, anchor `x-ts`), `fwd-vrising.sh` and `fwd-skyrim.sh`.
2. **Forwarding script.** Write `sidecars/fwd-dragonwilds.sh`, and keep a copy in the repo under `sidecar/`:
   ```sh
   #!/bin/sh
   # DNAT tailnet Dragonwilds traffic (udp game 7777, beacon 8888) to the Pterodactyl host ports
   set -e
   H=172.30.0.1
   for P in 7777 8888; do
     iptables -t nat -A PREROUTING -i tailscale0 -p udp --dport $P -j DNAT --to-destination $H:$P
   done
   iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
   exec /usr/local/bin/containerboot
   ```
3. **Compose service.** Back up the compose file. Insert a `dragonwilds` service before `networks:`:
   - `<<: *ts`, `container_name: dragonwilds-ts`, `hostname: dragonwilds`
   - Env: `TS_STATE_DIR=/var/lib/tailscale`, `TS_USERSPACE "false"`, `TS_HOSTNAME dragonwilds`, `TS_AUTH_ONCE "true"`, `TS_ACCEPT_DNS "false"`
   - Volumes: `sidecars/dragonwilds/state:/var/lib/tailscale` and `fwd-dragonwilds.sh:/fwd.sh:ro`

   Create the state dir. Validate the file with `docker compose config -q`.
4. **Start it.** Run `docker compose up -d --no-deps dragonwilds`. Check `docker ps` afterward to confirm no other sidecar was recreated, by comparing the "Up" times.
5. **Login.** The node needs a login: read the login URL from `docker logs dragonwilds-ts`, give it to Aaron, and **wait** for him to approve it. Do not use or create auth keys.
6. **Verify.**
   - `docker exec dragonwilds-ts tailscale ip -4` returns the node IP.
   - `iptables -t nat -L PREROUTING -n -v` inside the sidecar shows both rules.
   - From a tailnet machine, `nc -u -w1 <ip> 7777 <<< x` and the same for 8888 raise the packet counters. Check conntrack, which shows forwarding to `172.30.0.1`.
7. **Record.** Append to AGENT_LOG and add the node IP to the README. Report the IP.

**Done when:** the node is online, both DNAT counters increment from a tailnet probe, and no other container restarted.

---

## Phase 3: Metrics agent (Prometheus and Grafana)

**Goal:** Dragonwilds shows up in the existing Grafana, which is reachable at `http://grafana.<tailnet>.ts.net`. The stack is compose project `palworld_metrics` at `/mnt/cache/appdata/pterodactyl/metrics`.

The stack already has:
- **Prometheus** v3.15.1 with config `metrics/prometheus/prometheus.yml`. It has no lifecycle API, so reload with `docker kill -s HUP palworld_metrics-prometheus-1`.
- **cAdvisor** (cpu, memory, network), with relabel rules that map container UUIDs to a `server` label.
- **Python stdlib exporters** in `metrics/exporter/`, one per service, each run with `python:3.13.17-alpine` as uid 65534.
- **Grafana** 13.3.0, which loads dashboards from `metrics/grafana/dashboards/<Folder>/*.json` (folders from file structure).

### Steps

1. **Container metrics (no game API needed).**
   - Back up `prometheus.yml`.
   - Add a relabel rule to the `cadvisor` job: `{ source_labels: [name], regex: "<dragonwilds uuid>", target_label: server, replacement: Dragonwilds }`.
   - Reload with HUP and confirm `container_memory_working_set_bytes{server="Dragonwilds"}` returns data in Prometheus.
2. **Game metrics exporter (`dragonwilds_exporter.py`).** It must be stdlib only, listen on 9881, and follow `palworld_exporter.py`'s style.
   - The game has no API, so derive metrics from:
     - **Process up:** whether the server's log file was modified recently, or Wings state. The simplest robust option is to read `/mnt/cache/appdata/pterodactyl/wings/lib/states.json` mounted read-only (its value for the UUID is `running`).
     - **Players online:** parse the server log at `<volume>/RSDragonwilds/Saved/Logs/RSDragonwilds.log` (confirm the filename) for join and leave lines.
     - **World save age:** the newest `.sav` mtime in `SaveGames/`.
     - **Server version:** a label from the version log line.
   - **Do not guess the join/leave patterns.** Find them in a real log after Aaron's Phase 4 connect. Grep for `Join`, `Login`, `PostLogin`, `Logout` and `NotifyAcceptedConnection`, and record the exact lines in the repo README.
   - Until Phase 4 has happened, ship the exporter with only the up, save-age and version metrics, and add players afterward.
   - **Mounts:** mount the volume's `Saved/Logs` and `Saved/SaveGames` read-only. Do not mount the whole volume. The uid 65534 user must be able to read them; check the file modes. If they are not readable, run the exporter as `988:988` instead.
   - **Compose:** add a `dragonwilds-exporter` service to `metrics/docker-compose.yml` (back it up first). Start it with `docker compose up -d --no-deps dragonwilds-exporter`. Add a `dragonwilds` scrape job, then HUP Prometheus.
3. **Dashboard.** Create `metrics/grafana/dashboards/Dragonwilds/dragonwilds.json`. Copy the panel style from `Palworld/palworld.json` (same datasource UID and units). Panels:
   - Up
   - Players online (once available)
   - CPU % and memory, from cAdvisor with `server="Dragonwilds"`
   - Network rx/tx
   - Last save age
   - Version

   Grafana picks up file changes without a restart. Check it with the Grafana API using Aaron's admin credentials from `metrics/.env`, read on Tower only and never printed.
4. **Commit.** Copy the exporter, the compose snippet and the dashboard JSON into the repo, with no secrets. Append to AGENT_LOG.

**Done when:** Prometheus target `dragonwilds` is UP, cAdvisor series exist for `server="Dragonwilds"`, and the dashboard loads with data. The player metric is either VERIFIED against a real join or marked **NOT DONE**, with the reason given.

---

## Phase 4: Aaron (in-game test; not an agent)

1. Run the same game version as the server. The version line is in the Phase 1 report.
2. Open **Worlds → Direct** in game and enter `<dragonwilds tailscale IP>:7777`, or `dragonwilds:7777` if MagicDNS works in game. Join.
3. Once in game, claim admin with the admin password from the Panel's Startup tab, or check that `OwnerId` already grants owner rights.
4. If Direct connect fails over Tailscale:
   - Ask the metrics/server agent to capture the server log around the attempt.
   - Try from the LAN IP `192.168.1.211:7777` to separate a game problem from a Tailscale one.
   - The fallback, if Direct only works on a LAN, is a subnet route or exit node design. That decision goes back to Aaron.
5. When it works: in the Tailscale admin console, share the `dragonwilds` machine with friends. They connect the same way.
