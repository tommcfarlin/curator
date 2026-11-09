# First test on the real TV

This is the plan for the first supervised session with the real Frame. It runs from the Mac. Nothing is installed on the TV. Allow about 20 minutes.

## What is already proven

The Curator TV client and the `samsungtvws` library were tested end to end against a simulated Frame (`tests/sim_tv.py`). The tests cover pairing, the token file, and a Deny on the TV. They also cover the art list, upload, select, thumbnails, and delete. Two more tests cover a TV that is off and the full flow from phone to TV.

The simulator was built from the library code, not from a real TV. This session finds out whether the real TV answers the same way.

## Before you start

1. Turn the TV on. Normal TV mode is fine.
2. Keep the TV remote in your hand.
3. Make sure that the Mac is on the home Wi-Fi.
4. On the TV, open Settings > General > External Device Manager > Device Connection Manager. Set Access Notification to "First Time Only". If it is set to "Off", the TV never shows the Allow prompt.

All commands run in a Terminal on the Mac, in the project folder:

```bash
cd ~/Projects/02-tm/reframe/curator
```

The TV address and the token file are in `config/local.toml`. Git ignores that file.

## Step 1: Pair and read (changes nothing on the TV)

```bash
.venv/bin/python -m curator.probe
```

The TV shows a prompt that asks to allow "Curator". Press Allow on the remote within 30 seconds.

The command prints a short summary and saves the full answer in `data/probe/`. The summary shows the art API version and the Art Mode state. It also shows the number of pieces, the pieces by category, and the piece that is showing now.

Run the same command a second time. It must not show the Allow prompt again. If the prompt comes back, the token is not working. Stop and report it.

## Step 2: Upload one test card (the screen does not change)

```bash
.venv/bin/python -m curator.probe --upload-test
```

The command uploads a 3840 × 2160 test card with the date and time on it. It prints the content ID and how long the upload took. On the TV, the card must appear in Art Mode under My Photos.

## Step 3: Show the test card

```bash
.venv/bin/python -m curator.probe --show CONTENT_ID
```

Use the content ID from step 2. Then press the power button on the remote once, briefly, to go to Art Mode. The test card must fill the screen with no mat and no stretching.

## Step 4: Check standby

1. While the TV is in Art Mode, run step 1 again. Write down whether it answers.
2. Hold the power button until the screen goes fully dark. Wait one minute, then run step 1 again. It is expected to print "The TV does not answer". Curator then keeps photos in its queue until the TV is back.
3. Turn the TV back on.

## Step 5: Use the phone app with the real TV

```bash
.venv/bin/python -m curator
```

On a phone on the home Wi-Fi, open the address that the command prints. Send one photo with "Show on the TV right away" turned on. The photo must appear on the TV, and "On the TV" must list it as "Your photo". Then choose a Samsung piece in the app and make sure that the TV changes to it. Press Control-C in the Terminal to stop.

## Step 6: Clean up

Remove the test card:

```bash
.venv/bin/python -m curator.probe --delete CONTENT_ID
```

Keep `config/token.txt`. The Pi needs the same token later, or the TV asks for Allow again.

## If something goes wrong

- If no prompt appears, check Access Notification (see "Before you start"). Then run step 1 again.
- If Curator says that the TV did not allow it, open Device Connection Manager > Device List on the TV. Set Curator to Allow, then run step 1 again.
- If a command hangs, press Control-C and run it again. Each command uses a 15-second timeout.
- If the TV answers but a request fails, keep the files in `data/probe/` and the Terminal output. They show what the TV said.

## Record the results

| Question | Result |
|---|---|
| Art API version | |
| Allow prompt appeared once only | |
| Category ID of Samsung art | |
| Category ID of uploaded photos | |
| Upload time for the test card | |
| Test card shows in Art Mode, no mat, not stretched | |
| TV answers while in Art Mode | |
| TV answers after a full power off | |
| Phone upload and "Show on TV" work | |
