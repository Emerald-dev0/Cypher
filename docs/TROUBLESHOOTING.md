# Troubleshooting

Five transports, the usual failure modes, and what "works in debug, fails in
release" actually means. Absorbs the deleted `TEST_ALL_CONNECTIONS.md` (P1-C3).

## The node never comes up

1. Desktop shell: read the startup phase (`Locating` → `Starting` → `Waiting for /ping`).
2. The error screen shows which interpreter was tried (`usedInterpreter`).
3. Nothing hardcoded to one developer's `C:\Users\…\python.exe` — if Python is
   missing, install 3.11+ and ensure `py`/`python` is on PATH.
4. Port 5000 already in use: another node (or leftover) is running. Kill it.

## Phone cannot find the PC

| Transport | Address shape | If discovery is empty |
| --- | --- | --- |
| Same WiFi | RFC1918 | Type the IP printed by the node |
| Phone hotspot | `192.168.43.x` | PC must join the hotspot first |
| PC hotspot | `192.168.137.x` | Phone joins the PC's hotspot |
| USB tethering | `192.168.42.x` | Works with WiFi off |
| Manual | anything private | Host header must be loopback or this machine (P1-S4) |

Firewall: allow TCP 5000 on **private** profiles only. Public WiFi is out of
scope until TLS (P2-S1).

## Pairing fails

- Code is six digits and rotates after a successful pair.
- Five wrong attempts lock the IP out for a cooldown.
- Old installs with the published token: uninstall, delete
  `%APPDATA%\Cypher\paired_devices.json` and `internal_token`.

## Files 403

Paired devices only see **shared folders**. Add the folder in the desktop
Files tab. Paths outside that allowlist are 403 with
`"path is outside the shared folders"` — that is the sandbox (P1-S2), not a
bug.

## Works in debug, not in release (Android)

Release APKs are not exempt from cleartext HTTP. Debug/profile Flutter builds
are. Use a properly signed build and the network-security config that ships
with the app. Do not "fix" this by allowing cleartext to the public internet.

## Protocol mismatch

`GET /ping` returns `protocol_version`. The desktop shell refuses a node it
does not speak. Update both sides together.
