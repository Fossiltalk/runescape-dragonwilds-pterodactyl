#!/bin/bash

## RuneScape: Dragonwilds install script (Pterodactyl egg)
## Adapted from pelican-eggs/games-steamcmd runescape_dragonwilds (David Wolfe / Red-Thirten, MIT).
## Install container: ghcr.io/ptero-eggs/installers:debian

set -u
export HOME=/mnt/server
cd /tmp
mkdir -p "$HOME/steamcmd" "$HOME/steamapps"
curl -sSL -o steamcmd.tar.gz https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz
tar -xzf steamcmd.tar.gz -C "$HOME/steamcmd"
cd "$HOME/steamcmd"

# SteamCMD fails otherwise, even as root. Ownership is reset at the end.
chown -R root:root /mnt

BINARY_DIR=$HOME/RSDragonwilds/Binaries/Linux
BINARY_NAME=RSDragonwildsServer-Linux-Shipping

# Install/verify the server (app 4019830, anonymous). SteamCMD sometimes fails on
# its first run while it self-updates, so retry up to 3 times.
for attempt in 1 2 3; do
    ./steamcmd.sh +force_install_dir "$HOME" +login anonymous +app_update "${SRCDS_APPID}" validate +quit
    [[ -f "$BINARY_DIR/$BINARY_NAME" ]] && break
    echo "SteamCMD attempt $attempt did not produce the server binary, retrying..."
done

# 32 and 64 bit Steam client libraries
mkdir -p "$HOME/.steam/sdk32" "$HOME/.steam/sdk64"
cp -v linux32/steamclient.so "$HOME/.steam/sdk32/steamclient.so"
cp -v linux64/steamclient.so "$HOME/.steam/sdk64/steamclient.so"

if [[ ! -f "$BINARY_DIR/$BINARY_NAME" ]]; then
    echo -e "\n\nSteamCMD failed to install the RuneScape Dragonwilds Dedicated Server!"
    echo -e "\tTry reinstalling the server again.\n"
    exit 1
fi
chmod +x "$BINARY_DIR/$BINARY_NAME"
CRASHPAD=$HOME/RSDragonwilds/Plugins/Developer/Sentry/Binaries/Linux/crashpad_handler
[[ -f "$CRASHPAD" ]] && chmod +x "$CRASHPAD"
if [[ -f "$HOME/RSDragonwildsServer.sh" ]]; then
    chmod +x "$HOME/RSDragonwildsServer.sh"
    echo "Launcher: RSDragonwildsServer.sh present"
else
    echo "Launcher: RSDragonwildsServer.sh MISSING, use $BINARY_NAME directly"
fi

# Seed DedicatedServer.ini so Wings' ini parser has the section to edit.
# Never touch an existing file (it holds the generated ServerGuid).
INI_DIR=$HOME/RSDragonwilds/Saved/Config/LinuxServer
INI=$INI_DIR/DedicatedServer.ini
SECTION='[/Script/Dominion.DedicatedServerSettings]'
mkdir -p "$INI_DIR" "$HOME/RSDragonwilds/Saved/SaveGames"
if [[ ! -f "$INI" ]]; then
    printf '[SectionsToSave]\nbCanSaveAllSections=true\n\n%s\n' "$SECTION" > "$INI"
    echo "Seeded $INI"
elif ! grep -qF "$SECTION" "$INI"; then
    printf '\n%s\n' "$SECTION" >> "$INI"
    echo "Added $SECTION to existing $INI"
else
    echo "Kept existing $INI"
fi

chown -R 988:988 /mnt/server
echo -e "\nRuneScape Dragonwilds Dedicated Server successfully installed!\n"
exit 0
