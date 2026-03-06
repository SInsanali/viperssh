# ViperSSH

TUI SSH/SFTP connection manager with password caching, password vault, connection history, and keepalive.

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
  --last       Reconnect to the most recent connection
  --show-last  Show the most recent connection and exit
  --setup      Re-run first-time setup (symlink creation)
  --check      Check system dependencies
  -h, --help   Show help
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
| `v` | Password vault |
| `/` | Search hosts |
| `t` | Theme selector |
| `?` | Help |
| `Esc` | Back |
| `q` | Quit |

## Connection History

Press `r` to open a recent connections modal showing your last 10 connections, split into SSH and SFTP sections. Select any entry to reconnect using the original protocol.

History is stored locally in `.viper_history` and is not committed to version control.

## Password Vault

The vault stores per-environment passwords in an AES-encrypted file so you don't have to retype them on every connection.

### Setup

1. Press `v` in the TUI to open the vault modal
2. Press `e` to enable the vault
3. On next launch you'll be prompted to set a master password — this encrypts the vault

### Saving passwords

After a successful login, you'll be prompted to save the password before entering the shell. On future connections to the same environment, the password is auto-filled silently — no prompt appears.

If a saved password fails (e.g. it was changed on the server), you'll enter the new password manually and be prompted to update the vault. The actual password used during login is saved directly via a secure pipe — you never have to re-type it.

### Managing passwords

Press `v` to open the vault modal:
- `e` — toggle vault on/off
- `Enter` — set/update password for the selected environment
- `d` — delete a saved password
- `●` = password saved, `○` = no password

### Skipping the master password prompt

Create a `.viper_vault_pass` file containing your master password:

```bash
echo 'your-master-password' > .viper_vault_pass
chmod 600 .viper_vault_pass
```

The vault will unlock automatically on launch using this file.

### Files

| File | Purpose |
|------|---------|
| `.viper_vault` | AES-encrypted passwords |
| `.viper_vault_pass` | Optional master password file |
| `.viper_vault_config` | Vault enabled/disabled toggle |

All vault files are gitignored.
