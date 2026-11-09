# Curator

Curator hangs your own photos in the Art Mode of your Samsung The Frame. You pick photos on your phone, a Raspberry Pi on your home network prepares them, and the TV shows them in Art Mode like any Samsung artwork. You do not need a Samsung Art Store subscription.

## Warning

This project uses an unofficial interface. Samsung does not document it. A TV software update can break it without notice. If uploads stop after an update, update the `samsungtvws` library first.

## Status

Early. The phone web app, the worker and the retry queue run on a computer with a pretend TV. The real TV client is not written yet. See `docs/DESIGN.md`.

## Try it on your computer

This uses a pretend TV. It needs no TV and no Pi. In the page, tap the status pill at the top to switch the pretend TV on or off.

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -r requirements-dev.txt
```

```bash
.venv/bin/python -m curator --fake-tv --port 8087
```

Open `http://127.0.0.1:8087` in a browser. To open it from your phone, add `--bind 0.0.0.0` and use your computer's address on your Wi-Fi. The page has no login, so use that only on your home network. Press Control-C to stop the server.

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

## Set up the Pi

The steps are in [docs/DEPLOY.md](docs/DEPLOY.md). Do them after the first test on the real TV in [docs/TV-TEST.md](docs/TV-TEST.md).

## Secrets

`config/local.toml` and `config/token.txt` hold the TV address and the pairing token. Git ignores both. Never commit them.

## Network safety

The web page has no login. Use it only on your home network. Do not forward port 8080 on your router.

## Licenses

`samsungtvws` is LGPL-3.0. See `docs/DESIGN.md` for the check and the terms.
