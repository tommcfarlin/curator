# How Curator works

This page is for people who want to change the code.

## Parts

| Part | File |
| --- | --- |
| Entry point | `curator/__main__.py` |
| Setup wizard | `curator/setup.py` |
| Settings loader | `curator/config.py` |
| Web app and JSON API | `curator/web.py` |
| Phone page (one HTML file, no build step) | `curator/static/index.html` |
| Image resize, crop and size check | `curator/imaging.py` |
| Retry queue (SQLite) | `curator/queue.py` |
| Worker that talks to the TV | `curator/worker.py` |
| TV client and pretend TV | `curator/tv.py` |
| Record of the photos that Curator added | `curator/library.py` |
| Manual checks against a real TV | `curator/probe.py` |

## Flow

1. A person picks photos on the phone page.
2. `imaging.prepare_image` makes a 3840 x 2160 JPEG in `data/prepared/`.
3. The web app adds an upload job to the retry queue.
4. The worker takes the next job and opens a WebSocket to the TV on port 8002.
5. The worker uploads the JPEG. If the person asked, the worker also selects it.
6. If the TV does not answer, the job waits and runs again later.

## Images

- The Frame panel is 16:9, so every photo becomes 3840 x 2160.
- Fill screen mode (`crop`) fills the screen and trims the overflow. A focus point picks the part that stays.
- Show whole photo mode (`fit`) keeps the whole photo and adds a black matte.
- Curator applies the EXIF rotation first, so phone photos keep the right side up.
- Curator never stretches a photo. A photo that needs more than 2 times enlargement gets a "Too small" warning.
- On iPhone, Safari converts HEIC photos to JPEG before the upload.

## Retry queue

- After a failure, Curator tries again after 2, 5, 10, 20 and 30 seconds. Then it tries one time each minute.
- When the TV starts to answer again, Curator runs the waiting jobs at once.
- A request to show a photo expires after 10 minutes. An upload waits about 5 hours.
- The newest show request wins. It replaces older show requests that still wait.

## TV client

- Curator uses the art API of the `samsungtvws` library: upload, select, list and delete.
- The first connection can show an Allow prompt on the TV. Curator saves the pairing token in `config/token.txt`.
- Curator learns the hardware address of the TV and saves it in `data/tv-mac.txt`. If the TV gets a new address, Curator searches the network for that hardware address.
- Curator cannot turn the TV on. In standby, the TV leaves the network.

## Phone page

- The page works in Safari on iPhone and in Chrome on Android, with no app install. People can add it to the home screen.
- Text starts at 17 px and follows the text size of the phone. Tap targets are at least 44 px.
- Words are plain. The page shows no pixel counts and no camera file names.
- The page has no login. A name in Settings is only a label for the Activity list.
- Only photos that Curator added can be removed from the TV.

## Tests

The tests need no TV and no Pi. `tests/sim_tv.py` is a simulated Frame. The real `samsungtvws` client runs against it.

```bash
.venv/bin/python -m pytest
```

## Licenses of the dependencies

| Package | License |
| --- | --- |
| `samsungtvws` | LGPL-3.0 |
| Flask | BSD-3-Clause |
| waitress | ZPL-2.1 |
| Pillow | MIT-CMU (HPND) |
| segno | BSD-3-Clause |

Curator installs `samsungtvws` from PyPI as a normal dependency. It does not copy or change the code of the library. You can replace the library with another version.
