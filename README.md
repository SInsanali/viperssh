# ViperSSH

TUI SSH connection manager with password caching and keepalive.

## Install

```bash
git clone git@github.com:SInsanali/viperssh.git
cd viperssh
cp etc/hosts.yaml.example etc/hosts.yaml
# Edit etc/hosts.yaml with your hosts
./viperssh
```

On first run, you'll be prompted to create a symlink so you can run `viperssh` from anywhere.

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

`?` help | `/` search | `Enter` connect | `Esc` back | `q` quit | `t` themes
