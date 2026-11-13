# Install Curator on a Raspberry Pi

This guide installs Curator on a Raspberry Pi as a service that starts with the Pi. It takes about 15 minutes.

## What you need

- A Samsung The Frame on your home network. Curator was tested on a 2021 Frame (Tizen 6).
- A Raspberry Pi on the same network, with Raspberry Pi OS (Debian 12 or newer) and Python 3.11 or newer.
- A terminal on the Pi, through SSH or with a keyboard and a monitor.

## Before you start

1. Turn the TV on.
2. On your router, reserve a fixed address for the TV and for the Pi. If the router changes the TV address later, Curator searches for the TV, but a fixed address is more reliable.
3. On the TV, turn off Night Mode in the Art Mode options. If Night Mode is on, the TV turns the screen off in a dark room and Curator cannot reach it.

## Install

On the Pi, get the code:

```bash
sudo apt install -y git python3-venv
```

```bash
sudo git clone https://github.com/tommcfarlin/curator.git /opt/curator
```

```bash
sudo chown -R "$(id -un):$(id -gn)" /opt/curator
```

Run the install script:

```bash
/opt/curator/deploy/install.sh
```

The script creates a Python environment and installs the requirements. The first time, it asks two questions. It searches the network for the TV and shows each one that it finds. Choose your TV. Then accept the address that Curator listens on.

Then the script installs and starts the `curator` service. It uses sudo for this step. If sudo asks for your password, type it.

## Pair with the TV

On a phone on the home network, open the address that the setup printed, for example `http://192.168.1.10:8080`. The first time Curator connects, the TV can show an Allow prompt. Press Allow with the TV remote. Some TVs do not ask.

In Curator, open Settings to see a QR code for other phones.

## Answers without questions

A script or an AI agent can give the answers on the command line. Run this before `install.sh`:

```bash
cd /opt/curator && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
```

```bash
.venv/bin/python -m curator.setup --tv-host 192.168.1.20 --bind 192.168.1.10
```

Replace the two addresses with the address of your TV and the address of your Pi. If setup runs without a terminal and without `--tv-host`, it cannot ask its questions. It prints the TVs that it found, tells you to use `--tv-host`, and stops with exit code 1. It does not write a file. Then run `deploy/install.sh`. It keeps the file that setup wrote.

## Update

```bash
cd /opt/curator && git pull && deploy/install.sh
```

## Change the settings

The settings are in `/opt/curator/config/local.toml`. Git ignores this file. To start again, run `.venv/bin/python -m curator.setup --force`, then restart the service:

```bash
sudo systemctl restart curator
```

## If the TV gets a new address

Curator learns the hardware address of the TV the first time that it reaches the TV. It saves the address in `data/tv-mac.txt`. If the TV address changes later, Curator searches the network for that hardware address, at most one time each minute. The TV must be on. To stop the changes, reserve an address for the TV on the router and put that address in `config/local.toml`.

## Make sure that it runs

```bash
systemctl status curator
```

```bash
journalctl -u curator -n 50
```

## The pairing token

If the TV gives Curator a token after you press Allow, Curator saves it in `config/token.txt`. The token lets a device on your network control the TV art, so only its owner can read the file. Git ignores it. If you lose it, delete the file and press Allow on the TV again.

## Limits

- Curator cannot turn the TV on. When the screen is black, the TV leaves the network. Turn the TV on with the remote. Photos that you send in the meantime wait. When the TV answers, Curator sends them.
- The page has no login. Use Curator on your home network only.
