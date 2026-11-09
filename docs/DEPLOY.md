# Deploy Curator to the Pi

Do this after the first test on the real TV ([TV-TEST.md](TV-TEST.md)) passes. Each step that connects to the Pi needs the owner's approval first.

The Pi is a Raspberry Pi 4 with Debian 12 and Python 3.11. Its user is `pi`, and its home Wi-Fi address is 192.168.1.10. The Mac reaches it with the SSH alias `curator-pi`.

## Files

- `deploy/push.sh` runs on the Mac. It copies the code to `/opt/curator` on the Pi. It never copies `config/local.toml`, `data/` or `.venv/`. With `--token`, it also copies the TV token.
- `deploy/install.sh` runs on the Pi. It creates the virtual environment, installs the requirements, and installs the systemd service. It is safe to run again after each update.
- `deploy/pi.toml` is the settings file for the Pi. `install.sh` copies it to `config/local.toml` once.
- `deploy/curator.service` is the systemd service. It runs as `pi`. It can write only `/opt/curator/data` and `/opt/curator/config`.

## Before the first deploy

1. On the router, give the Pi a fixed address (192.168.1.10). Curator listens on that address only, so it stays off Tailscale.
2. Finish [TV-TEST.md](TV-TEST.md), so that `config/token.txt` exists on the Mac.

## First deploy

On the Pi, make the folder once. If sudo asks for your password, type it:

```bash
sudo install -d -o pi -g pi /opt/curator
```

On the Mac, copy the code and the token:

```bash
deploy/push.sh --token
```

On the Pi, install and start the service:

```bash
/opt/curator/deploy/install.sh
```

On a phone on the home Wi-Fi, open `http://192.168.1.10:8080`. Settings in Curator shows a QR code for other phones.

## Updates

On the Mac:

```bash
deploy/push.sh
```

On the Pi:

```bash
/opt/curator/deploy/install.sh
```

## Check the service

On the Pi:

```bash
systemctl status curator
```

```bash
journalctl -u curator -n 50
```

## The pairing token

The TV gives one token to Curator after you press Allow. The Mac and the Pi use the same token, so the TV does not ask again. The token lets a device on the network control the TV art, so the file is readable by its owner only (mode 600). Git ignores it. If you lose it, run the pairing step in [TV-TEST.md](TV-TEST.md) again.
