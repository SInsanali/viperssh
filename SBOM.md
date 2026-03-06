# ViperSSH — Software Bill of Materials

Generated from the project virtual environment. All packages are installed
automatically when you first run `./viperssh`.

## Direct dependencies

These are declared in `requirements.txt`:

| Package | Version | Purpose |
|---------|---------|---------|
| cryptography | >=41.0 | AES encryption for password vault (Fernet + PBKDF2) |
| PyYAML | >=6.0 | Parse `etc/hosts.yaml` configuration |
| textual | 7.3.0 | Terminal UI framework |
| rich | 14.2.0 | Rich text rendering (used by textual) |
| Pygments | 2.19.2 | Syntax highlighting (used by rich) |

## Transitive dependencies

Pulled in automatically by direct dependencies:

| Package | Version | Required by |
|---------|---------|-------------|
| cffi | 2.0.0 | cryptography |
| pycparser | 2.23 | cffi |
| linkify-it-py | 2.0.3 | textual |
| markdown-it-py | 3.0.0 | textual / rich |
| mdit-py-plugins | 0.4.2 | textual |
| mdurl | 0.1.2 | markdown-it-py |
| platformdirs | 4.4.0 | textual |
| typing_extensions | 4.15.0 | textual / cryptography |
| uc-micro-py | 1.0.3 | linkify-it-py |

## System dependencies

| Tool | Required | Purpose |
|------|----------|---------|
| python3 | Yes | Runtime (3.8+) |
| ssh | Yes | SSH connections |
| sftp | No | SFTP connections (bundled with openssh) |
| expect | No | Password caching and auto-fill |

## Setup

```bash
git clone git@github.com:SInsanali/viperssh.git
cd viperssh
cp etc/hosts.yaml.example etc/hosts.yaml
./viperssh
```

The wrapper script creates a virtual environment and installs all Python
dependencies on first run. No manual `pip install` needed.
