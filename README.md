# RuneScape: Dragonwilds on Pterodactyl

A Pterodactyl egg for the [RuneScape: Dragonwilds](https://dragonwilds.runescape.wiki/w/Dedicated_Servers/Linux) dedicated server (Steam app 4019830, native Linux), reached by friends over Tailscale.

- **Egg:** [`egg-runescape-dragonwilds.json`](egg-runescape-dragonwilds.json), adapted from [pelican-eggs/games-steamcmd](https://github.com/pelican-eggs/games-steamcmd/tree/main/runescape_dragonwilds) (MIT).
- **Image:** `ghcr.io/ptero-eggs/steamcmd:debian` (public). Install container: `ghcr.io/ptero-eggs/installers:debian`.
- **Ports:** UDP 7777 (game, `-Port`) and UDP 8888 (world settings beacon, `-BeaconPort`). Host and container ports must match, or players are kicked to the title screen.
- **Install script:** [`scripts/install.sh`](scripts/install.sh) (the same script that is embedded in the egg).
- **Plan and history:** [`BRIEFS.md`](BRIEFS.md).

## How the egg works

- **Install:** SteamCMD installs app 4019830 anonymously into the volume (about 5 GB on disk), retrying up to 3 times because SteamCMD's first run often fails with `Missing configuration`. The script then seeds `RSDragonwilds/Saved/Config/LinuxServer/DedicatedServer.ini` with `[SectionsToSave]` and the `[/Script/Dominion.DedicatedServerSettings]` header if the file does not exist, and chowns everything to 988:988. An existing INI is never touched.
- **Start:** `./RSDragonwildsServer.sh -log -Port={{SERVER_PORT}} -BeaconPort={{BEACON_PORT}} -ini:Game:[/Script/Engine.GameSession]:MaxPlayers={{MAX_PLAYERS}}`. The launcher script ships with the Steam app and runs `RSDragonwilds/Binaries/Linux/RSDragonwildsServer-Linux-Shipping RSDragonwilds`.
- **Config:** on every start, Wings' `ini` parser writes `OwnerId`, `ServerName`, `DefaultWorldName`, `AdminPassword` and `WorldPassword` from the Panel variables into `DedicatedServer.ini`, as `Key = Value`. Wings handles the section name with `/` and `.`. The game reads the spaced format and rewrites the file a few seconds later as `Key=Value`. It drops `AdminPassword` from the file when it rewrites it, and Wings writes it back on the next start. The egg never writes `ServerGuid`, `KnownPlayerList` or `AdministratorList`, so the server's own values survive.
- **Edits while running are lost.** The server rewrites the INI. Stop it first, or change the Panel variables.
- **Done string:** `CREATE SESSION - Advertise` (logged about 10 s after start, after `World settings beacon listening on port 8888`).
- **Stop:** `^C` (SIGINT). The image's `tini -g` passes it to the whole process group. The engine shuts down cleanly in about 1 s (`LogExit: Exiting.`, `RequestExit(bForce=false, ReturnCode=130)`), and the container exits with code 130. **It does not write a final save.** Tested on 2026-11-22 with no players connected; the `.sav` mtime did not change. SIGTERM is worse: the process dies with no shutdown log, and Wings treats it as a crash and restarts it. Back up only after a clean stop, and expect to lose play since the last autosave.
- **Owner ID in logs:** the game prints `OwnerId` in the console and in `Saved/Logs/RSDragonwilds.log`. Don't post those logs publicly.
- **Saves:** `RSDragonwilds/Saved/SaveGames/*.sav`. On start the server loads the newest `.sav`, or creates a world named after `DEFAULT_WORLD_NAME`. Never rename a `.sav`.

- **Verified version:** game build 1.0.2.2 (`LogNetVersion: Set ProjectVersion to 1.0.2.2`), Steam build id 26670300, engine `5.6.1-261625+++dominion+hotfix`. Players need the same game version.

## Variables

| Variable | Default | Notes |
|---|---|---|
| `SERVER_NAME` | `Dragonwilds` | "Created By" column, max 16 characters |
| `DEFAULT_WORLD_NAME` | `Default World` | Name of a newly created world |
| `OWNER_ID` | blank | **Required.** 32-character Player ID (Settings in game, copy button). Never commit it. |
| `ADMIN_PASSWORD` | blank | **Required**, at least 12 characters. Hidden from the user view; admins see it under Admin → Servers → *server* → Startup. |
| `WORLD_PASSWORD` | blank | Leave empty: joining password-protected servers is flaky, and Tailscale node sharing is the access control. |
| `MAX_PLAYERS` | `6` | 1–6 |
| `BEACON_PORT` | `8888` | Must equal the server's second allocation. Not user-editable. |
| `AUTO_UPDATE` | `0` | Updates are manual; see below. |

## Setup

1. Panel → Admin → Nests → **Create** "Dragonwilds" → **Import Egg**, and choose the JSON file in this repo.
2. Add allocations `0.0.0.0:7777` and `0.0.0.0:8888` to the node. Do not forward them on the router; access is Tailscale only.
3. Create a server from the egg: primary allocation 7777, extra allocation 8888, about 10 GB RAM (2 GB plus 1 GB per player, with headroom), 400% CPU, 20 GB disk.
4. Set `OWNER_ID` and an admin password (`openssl rand -base64 18`). Leave `WORLD_PASSWORD` empty.
5. Wait for the install (several minutes), then start. The server is ready when the console shows the done string.

## Tailscale (no port forwarding)

Tower is behind CGNAT, so the public Worlds list (advertised through Epic Online Services with the public IP) **does not work**. Friends use the **Direct** tab instead.

A Tailscale sidecar node `dragonwilds` on `pterodactyl_nw` DNATs UDP 7777 and 8888 from the tailnet to the host ports, like the `skyrim` and `vrisingserver` sidecars. The sidecar files are in [`sidecar/`](sidecar/). Tower's live node: `dragonwilds` = `100.109.134.72`.

First login: containerboot only waits 60 s for an interactive login, so the link expires before it can be approved. Log the node in once with a one-off userspace `tailscale up --timeout=0` container on the same state dir, remove it, then start the sidecar. Share the `dragonwilds` node with friends from the Tailscale admin console.

## Updating

`AUTO_UPDATE` defaults to 0. A silent update can leave the server on a different version than friends' clients.

1. Check the current game version (Steam news or the wiki) and agree with the group to update.
2. Stop the server. Confirm a `.sav` in `SaveGames/` was just written.
3. Back it up (see below).
4. Set `AUTO_UPDATE` to 1 and start once, or use Settings → Reinstall Server (the install script runs SteamCMD `validate` and keeps the INI and saves).
5. Check the version line in the console, then set `AUTO_UPDATE` back to 0.
6. Test with one player before telling the group.

## Backups

Back up `RSDragonwilds/Saved/SaveGames/` and `RSDragonwilds/Saved/Config/LinuxServer/DedicatedServer.ini` (it holds the `ServerGuid`). The volume is at `/mnt/cache/appdata/pterodactyl/wings/lib/volumes/<server-uuid>/` on Tower. Use Pterodactyl's backup feature or add those paths to the existing backup job; skip the game files, which SteamCMD can reinstall. The server saves about every 5 minutes, so back up after a clean stop.

## For friends: how to connect

1. Accept the Tailscale node share for `dragonwilds` and keep Tailscale running.
2. Run the same game version as the server.
3. In game, open **Worlds → Direct** and enter `100.109.134.72:7777`. Then join.

Direct join over Tailscale is verified (2026-11-22 and 2026-11-24).

**Always type the address in the Direct tab. Do not use the Recent servers list.** A Recent entry reconnects through the EOS session, which hands out Tower's public IP. Behind CGNAT that attempt never reaches Tower, and the game shows "Connection lost / network connection was interrupted". The same Direct address works immediately (2026-11-24).
