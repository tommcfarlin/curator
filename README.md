# Frame Art Pi

A small service for a Raspberry Pi. You upload your own images from a phone or computer. The service sends them to the Art Mode of a Samsung The Frame. You do not need a Samsung Art Store subscription.

## Warning

This project uses an unofficial interface. Samsung does not document it. A TV software update can break it without notice. If uploads stop after an update, update the `samsungtvws` library first.

## Status

Early. The image module and the retry queue work and have tests. The TV client, web page, folder watcher and service are not written yet. See `docs/DESIGN.md`.

## Run the tests on your computer

The tests do not need a TV or a Pi.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements-dev.txt
```

```bash
.venv/bin/python -m pytest
```

## Set up the Pi (planned)

These steps are a plan. The Pi model, the OS and the SSH access are not known yet. Do not follow them until the service code is complete.

1. Install Raspberry Pi OS and make sure that the Pi has Python 3.10 or newer.
2. Copy this folder to `/opt/frame-art-pi` on the Pi.
3. Create the virtual environment and install the requirements.
4. Copy `config/example.toml` to `config/local.toml`. Set the TV address.
5. Start the service by hand once. The TV shows an Allow prompt. Approve it with the remote.
6. Copy `deploy/frame-art-pi.service` to `/etc/systemd/system/`. Edit the user and paths if needed.
7. Run `sudo systemctl enable --now frame-art-pi`.
8. Open `http://raspberrypi.local:8080` on your phone.

## Secrets

`config/local.toml` and `config/token.txt` hold the TV address and the pairing token. Git ignores both. Never commit them.

## Network safety

The web page has no login. Use it only on your home network. Do not forward port 8080 on your router.

## Licenses

`samsungtvws` is LGPL-3.0. See `docs/DESIGN.md` for the check and the terms.
