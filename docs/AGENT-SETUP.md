# Install Curator with an AI agent

You are helping a person install Curator on their Raspberry Pi. Curator is a small Flask app. It sends the owner's photos to the Art Mode of a Samsung The Frame TV over the home network. The code is at https://github.com/tommcfarlin/curator (public, MIT license).

Read this whole file before you start. Then work through the steps with the person.

## Goal

At the end, these must be true:

- The `curator` systemd service is active on the Pi.
- The page at http://PI_ADDRESS:8080 opens on the person's phone.
- The On the TV tab lists the art that is on the TV.

## Rules for you

- Ask the person before each step that changes the Pi or uses sudo.
- Tell the person what a command does before you run it.
- The person types any password. Never type a password for them.
- Never put addresses, tokens, or the details of the person into git or into the repo files. Put them only in `config/local.toml` (git ignores it) and `config/token.txt`.
- Do not make the repo or any data public.
- Use only the commands in this file. If a command fails, read the Troubleshooting section. Then ask the person.

## Facts to collect first

Ask the person for these facts before you run anything:

| Fact | Why you need it |
| --- | --- |
| How you reach the Pi: you run on the Pi, or you use SSH (host and user) | Every command below runs on the Pi. |
| The TV is on and shows Art Mode or a picture | When the screen is black, the TV leaves the network. |
| The Pi and the TV are on the same network | Curator cannot cross networks or guest Wi-Fi. |
| The TV address (optional) | Setup can find the TV, so the person can skip this. |

In this file, 192.168.1.20 is an example TV address and 192.168.1.10 is an example Pi address. Use the real addresses of the person.

## Steps

Run each command on the Pi.

### 1. Check the system

Run this command:

```bash
cat /etc/os-release
```

Make sure that the output names Raspberry Pi OS or Debian 12 or newer.

Run this command:

```bash
python3 --version
```

Make sure that the output is `Python 3.11` or newer. If it is older, stop and tell the person. Curator needs Python 3.11 or newer.

### 2. Install the tools

Ask the person first. This step uses sudo.

```bash
sudo apt install -y git python3-venv
```

Make sure that the command ends without an error.

### 3. Get the code

Ask the person first. These commands use sudo.

```bash
sudo git clone https://github.com/tommcfarlin/curator.git /opt/curator
```

Make sure that the folder `/opt/curator` exists and has the file `requirements.txt`.

Give the folder to the person who runs Curator:

```bash
sudo chown -R "$(id -un):$(id -gn)" /opt/curator
```

Make sure that `ls -ld /opt/curator` shows the name of the person as the owner.

### 4. Create the Python environment

Run this command:

```bash
cd /opt/curator && python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
```

Make sure that the command ends without an error and that `/opt/curator/.venv/bin/python` exists.

### 5. Find the Pi address

Run this command:

```bash
hostname -I
```

Make sure that the output has an address like 192.168.1.10. If the output has more than one address, pick the one on the home network. If you are not sure, ask the person. This is PI_ADDRESS in the rest of this file.

### 6. Find the TV and write the settings file

Make sure that the TV is on. Then choose one of the two ways.

Way A, with questions. This is the easier way. Run this command:

```bash
cd /opt/curator && .venv/bin/python -m curator.setup
```

Setup searches the /24 network for devices that answer on TCP port 8002. For each one, it reads the model name from the TV. It prints a numbered list. Ask the person which line is their TV. Type the number, or press Enter for the first one. Then accept the listen address, or type PI_ADDRESS.

Make sure that the output ends with `Wrote` and the path `config/local.toml`.

Way B, without questions. When you know the TV address, use this way. To find the TV address, do one of these:

- Run Way A once and read the list.
- Look in the router for a device that is named like a Samsung TV.
- Ask the person to open the TV menu Settings > General > Network > Network Status.

Then run this command. Use the real addresses.

```bash
cd /opt/curator && .venv/bin/python -m curator.setup --tv-host 192.168.1.20 --bind 192.168.1.10
```

Make sure that the output says `Wrote` and the path `config/local.toml`.

If setup says that the file exists, ask the person. If they agree to replace it, add `--force` to the command. The other flags are `--port` (the default is 8080) and `--config`.

### 7. Install the service

Ask the person first. The script uses sudo. If sudo asks for a password, the person types it.

```bash
/opt/curator/deploy/install.sh
```

Make sure that the output ends with `Curator is installed in /opt/curator.` The script keeps the settings file that setup wrote.

### 8. Make sure that the service runs

Run this command:

```bash
systemctl is-active curator
```

Make sure that the output is `active`.

Run this command. Use the real Pi address.

```bash
curl -s http://192.168.1.10:8080/api/status
```

Make sure that the output is JSON. When the TV is on, the JSON has `"tv_online": true`.

## Steps only the person can do

Tell the person to do these. You cannot do them.

1. Press Allow with the TV remote. The first time Curator connects, the TV can show an Allow prompt. Some TVs do not ask. Curator saves the pairing token in `config/token.txt`.
2. Reserve a fixed address for the TV and for the Pi in the router. Without this, the router can change the addresses later.
3. Turn off Night Mode in the Art Mode options on the TV. If Night Mode is on, the TV turns the screen off in a dark room and Curator cannot reach it.
4. Open http://PI_ADDRESS:8080 on the phone. Use the home Wi-Fi. Then add the page to the home screen. On an iPhone, use Share > Add to Home Screen. On Android, use the browser menu > Add to Home screen.
5. Open the On the TV tab. Make sure that it lists the TV art.

## Troubleshooting

| Problem | Cause and fix |
| --- | --- |
| `tv_online` is false | The TV is off or the screen is black. The TV leaves the network in standby and Curator cannot turn it on. Ask the person to turn the TV on with the remote. When the TV answers, Curator sends the photos that wait in the queue. |
| `tv_online` stays false with the TV on | The TV address is wrong. Run `cd /opt/curator && .venv/bin/python -m curator.setup --force`. Then run `sudo systemctl restart curator`. Curator also searches for the TV by its hardware address one time each minute, so a new TV address is often found without help. |
| Setup finds no TV | The TV is off, or the TV is on a different network or VLAN, or guest Wi-Fi isolation blocks the Pi. Put the Pi and the TV on the same network. Turn the TV on. Run setup again. Or use the TV address from the TV menu with `--tv-host`. |
| The page does not open on the phone | The bind address is wrong, or the phone is on a guest network. Make sure that `bind` in `/opt/curator/config/local.toml` is PI_ADDRESS. Put the phone on the same network as the Pi. |
| The service fails | Run `journalctl -u curator -n 50` and read the last lines. Then ask the person before you change anything. |
| `Curator does not know the TV address` | The settings file has no TV address. Run `cd /opt/curator && .venv/bin/python -m curator.setup`. |

## Update

When the person wants a newer version, ask first. Then run this command:

```bash
cd /opt/curator && git pull && deploy/install.sh
```

The script keeps `config/local.toml` and `config/token.txt`.

## Limits to tell the person

- Curator cannot turn the TV on.
- The page has no login. Use Curator on the home network only.
