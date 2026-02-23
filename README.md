# ViperSSH

TUI SSH/SFTP connection manager with password caching, connection history, and keepalive.

## Install

```bash
git clone git@github.com:SInsanali/viperssh.git
cd viperssh
cp etc/hosts.yaml.example etc/hosts.yaml
# Edit etc/hosts.yaml with your hosts
./viperssh
```

On first run, you'll be prompted to create a symlink so you can run `viperssh` from anywhere.

## Usage

```
viperssh [OPTIONS]

Options:
  --setup    Re-run first-time setup (symlink creation)
  --check    Check system dependencies
  -h, --help Show help
```

## Dependencies

**Required:** python3, ssh, sftp

**Optional:** expect (enables password caching for SSH and SFTP)

Run `viperssh --check` to verify dependencies are installed.

## Uninstall

1. Delete the folder
2. Remove the symlink (if created): `rm ~/bin/viperssh` or `rm ~/.local/bin/viperssh`

## Config

Edit `etc/hosts.yaml`:

```yaml
environments:
  Dev:
    suffix: .dev.example.local
    hosts:
      - bastion1
      - appserver1
  Prod:
    suffix: .prod.example.local
    hosts:
      - prodserver1
```

## Keys

| Key | Action |
|-----|--------|
| `↑↓` / `j k` | Navigate |
| `Enter` | Connect via SSH |
| `s` | Connect via SFTP |
| `r` | Recent connections |
| `/` | Search hosts |
| `t` | Theme selector |
| `?` | Help |
| `Esc` | Back |
| `q` | Quit |

## Connection History

Press `r` to open a recent connections modal showing your last 10 connections, split into SSH and SFTP sections. Select any entry to reconnect using the original protocol.

History is stored locally in `.viper_history` and is not committed to version control.
