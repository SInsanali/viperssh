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

## Connecting

With `expect` installed, each stage of the connection is reported as it happens:

```
[VIPERSSH] Connecting to app1.dev.example.local

  Proxy jump via bastion ................................ [ OK ]
  Connecting to app1.dev.example.local .................. [ OK ]
  Authenticating bob@app1.dev.example.local ............. [ OK ]
```

Jump hosts are read from `~/.ssh/config` (`ProxyJump`, or `ProxyCommand ssh -W ...`). If a password is rejected you're asked for it again; on failure, ssh's error is shown under the failed step.

When the session ends, a closing line says so and, if you didn't log out yourself, why it ended:

```
[VIPERSSH] Disconnected from app1.dev.example.local
[VIPERSSH] Disconnected from app1.dev.example.local: logged out for inactivity
[VIPERSSH] Disconnected from app1.dev.example.local: closed by the server
[VIPERSSH] Lost connection to app1.dev.example.local: the server stopped responding
```

### Expired passwords

If the server says your password has expired, ViperSSH walks you through changing it: it answers the current-password prompt, asks for the new password twice (catching typos before they use up the server's retries), and shows the server's reason if it refuses one. If the server signs you out after the change, ViperSSH reconnects with the new password and offers to save it to the vault.

This works with local accounts (pam_unix) and FreeIPA accounts (sssd). IPA checks a new password against its policy only after you've entered it twice; if it refuses, ViperSSH shows IPA's message and lets you try another, logging back in with your old password when the server needs that. When the bastion and the target share an IPA account, the new password is used on both.

## Connection History

Press `r` to open a recent connections modal showing your last 10 connections, split into SSH and SFTP sections. Select any entry to reconnect using the original protocol.

History is stored locally in `var/history.json` and is not committed to version control.

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

Create a `var/vault/master` file containing your master password:

```bash
echo 'your-master-password' > var/vault/master
chmod 600 var/vault/master
```

The vault will unlock automatically on launch using this file.

### Files

| File | Purpose |
|------|---------|
| `var/vault/vault.enc` | AES-encrypted passwords |
| `var/vault/master` | Optional master password file |
| `var/vault/config` | Vault enabled/disabled toggle |

All runtime state lives under `var/` and is gitignored.

## Development

```bash
./tests/run_tests.sh         # test suite
./tests/preview.sh           # list simulated connection scenarios
./tests/preview.sh expired   # preview the connection output for one (password: hunter2)
```

`tests/preview.sh` runs `bin/expect.sh` against a fake `ssh` (`tests/fake_ssh/ssh`), so connection output — proxy jumps, rejected and expired passwords, connection failures — can be checked without a live host.

For real servers, `tests/e2e/run.sh` runs sshd in Docker (Rocky Linux and Ubuntu with local accounts, plus an optional FreeIPA server) and connects with a copy of this working tree, leaving your own vault, history and `~/.ssh` alone:

```bash
tests/e2e/run.sh up ipa              # start the servers (FreeIPA's first start takes a few minutes)
tests/e2e/run.sh connect ipa         # or rhel-jump, rhel-kbd, ubuntu, ipa-jump, ... (bob / hunter2)
tests/e2e/run.sh state ipa expired   # reset a server's password state
tests/e2e/run.sh down
```

Run `tests/e2e/run.sh` with no arguments for the full list of hosts and commands.
