# Pi access plan

Goal: let Claude run commands on the Pi over SSH, with no password in chat and no key shared by accident. Nothing here has been done yet. Claude does not connect to the Pi until you say so.

## What we need to know

The Pi model, the OS version, the host name or IP address, and the user name. Run these on the Pi (monitor and keyboard, or an existing SSH session) and send the output:

```bash
cat /etc/os-release
```

```bash
cat /proc/device-tree/model; echo
```

```bash
hostname -I
```

```bash
python3 --version
```

## Make a key just for Curator

Run this on your Mac. It makes a key that is used only for this Pi, with no passphrase prompt in the way of automation. Press Enter at the passphrase question only if you accept that anyone with the file can log in.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/curator_pi -C "curator-pi"
```

## Install the key on the Pi

You type the Pi password yourself. Replace the user and address.

```bash
ssh-copy-id -i ~/.ssh/curator_pi.pub USER@PI_ADDRESS
```

Test it. A successful login prints the Pi host name and asks for no password.

```bash
ssh -i ~/.ssh/curator_pi -o IdentitiesOnly=yes USER@PI_ADDRESS hostname
```

## Add a short name

Add this block to `~/.ssh/config` on your Mac.

```
Host curator-pi
    HostName PI_ADDRESS
    User USER
    IdentityFile ~/.ssh/curator_pi
    IdentitiesOnly yes
```

After that, `ssh curator-pi` works. Claude would use only this name.

## Hardening (optional, after it works)

Turn off password login on the Pi once the key works. Edit `/etc/ssh/sshd_config`, set `PasswordAuthentication no`, then run `sudo systemctl restart ssh`. Keep a second session open while you test, so a mistake does not lock you out.

## Rules for Claude

Claude connects only after you give a clear yes in chat. Claude does not ask for or type passwords. Claude does not change SSH settings or install software on the Pi without asking first.
