# ViperSSH

A TUI SSH connection manager with password caching and keepalive.

## Quick Start

1. Clone the repository
2. Copy example configs:
   ```bash
   cp etc/suffixes.conf.example etc/suffixes.conf
   cp etc/host_list/Example.hosts.example etc/host_list/Dev.hosts
   ```
3. Edit the configs with your environments and hosts
4. Run: `./viperssh`

## Configuration

### etc/suffixes.conf

Maps environment names to FQDN suffixes:
```
Dev=.dev.example.local
Test=.test.example.local
Prod=
```
Leave the value blank if no suffix is needed.

### etc/host_list/*.hosts

One file per environment. The filename (without `.hosts`) must match an entry in `suffixes.conf`:
```
bastion1
appserver1
database1
```
Short hostnames get the suffix appended. FQDNs (containing `.`) or `user@host` format are used as-is.

## Key Bindings

| Key | Action |
|-----|--------|
| `?` or `h` | Toggle help menu |
| `/` | Search/filter hosts |
| `Enter` or `Right` | Select / Connect |
| `Esc` or `Left` | Back |
| `q` | Quit |
| `Tab` | Switch panels |
| `UP`/`DOWN` or `j`/`k` | Navigate (vim-style) |
| `t` | Theme selector |

## Features

- Password entered once, cached for session (handles bastion hops)
- 180-second keepalive (prevents idle disconnects)
- SSH banner/MOTD suppression
- Auto-accept host key prompts
- Multiple color themes (Viper, Ocean, Sunset, Matrix, Frost)
