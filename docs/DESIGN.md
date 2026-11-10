# Design: Curator

## Goal

A small service on a Raspberry Pi. You upload your own images from a phone or computer. The service sends them to the Art Mode of a Samsung The Frame over the home network. You do not need a Samsung Art Store subscription.

The TV is a 2021 The Frame, model QN55LS03AAFXZA, Tizen 6.0, at 192.168.1.20.

## Status

Stage 1 is done: the web app, the worker, the retry queue and a fake TV run on the Mac. The real TV client (`SamsungTV` in `curator/tv.py`) is tested end to end with the real `samsungtvws` library against a simulated Frame (`tests/sim_tv.py`). There are 92 tests. The first run on the real TV passed (see [TV-TEST.md](TV-TEST.md)). The next step is [TV-TEST.md](TV-TEST.md) for the rest, then [DEPLOY.md](DEPLOY.md). The Pi has SSH access but no Curator code.

Plan: (1) build and test on the Mac with the fake TV (done), (2) one supervised check against the real TV, (3) deploy to the Pi with systemd, (4) switch the Pi to the real TV.

## Parts

| Part | File | Status |
| --- | --- | --- |
| Image resize, crop and size check | `curator/imaging.py` | done, tested |
| Retry queue (SQLite) | `curator/queue.py` | done, tested |
| Settings loader | `curator/config.py` | done, tested |
| Record of Curator uploads | `curator/library.py` | done, tested |
| TV interface and fake TV | `curator/tv.py` | done (fake only) |
| Worker | `curator/worker.py` | done, tested |
| Web app and JSON API | `curator/web.py`, `curator/static/index.html` | done, tested |
| Entry point | `curator/__main__.py` | done (`--fake-tv` only) |
| Real TV client | `curator/tv.py` | planned (stage 2) |
| Folder watcher | `curator/watch.py` | planned (after version 1) |

## Flow

1. An image arrives from the web page or the watched folder.
2. `imaging.prepare_image` makes a 3840x2160 JPEG in `data/prepared/`.
3. The service adds a job to the retry queue.
4. The worker takes the next due job and opens a WebSocket to the TV on port 8002.
5. The worker uploads the JPEG, selects it, and marks the job done.
6. If the TV is off or refuses, the worker records the error. The job runs again later after a longer delay.

## Image rules

- The Frame panel is 16:9, so the target size is 3840x2160.
- Mode `crop` (default) fills the screen and cuts the overflow. A focus point picks which part stays.
- Mode `fit` shows the whole image and fills the rest with a black matte.
- The module applies the EXIF rotation first, so phone photos keep the right side up.
- The output is always JPEG, quality 92. This keeps files small for the upload.
- HEIC is not supported. Phone browsers usually convert it to JPEG on upload.

## Photo size rules

- Best: 3840 x 2160 pixels or larger (4K, 16:9). Minimum: 1920 x 1080.
- The page tells you the size rule on the Add screen, before you pick photos.
- After you pick a photo, the page shows one of three results on its card: "Looks sharp" (no enlargement), "Good enough" (enlarged up to 2 times) or "Too small" (enlarged more than 2 times, so it can look blurry).
- The check uses the part of the photo that the Frame shows. In Fill screen mode that is the trimmed part. A tall phone photo can pass in Show whole photo mode and fail in Fill screen mode. The message then suggests Show whole photo.
- If Fill screen mode trims more than 35% of a photo, the card says how much it trims.
- Curator never stretches a photo, so a photo cannot look squashed. The only quality problem is blur from enlargement.
- A "Too small" photo can still be sent. The card warns you, and you can remove it. We can make this a hard block later.
- The rules live in `curator/imaging.py` (`assess`) and are tested. The prototype page copies the same numbers.

## Retry queue

- The queue is a SQLite file. It is in the Python standard library, so it adds no dependency.
- After a failure, Curator tries again after 2 s, 5 s, 10 s, 20 s and 30 s. After that, it tries one time each minute.
- When the TV starts to answer again, Curator runs the waiting jobs immediately.
- Curator drops a "show" request that waited longer than 10 minutes. An upload stays in the queue for about 5 hours.
- After 300 failed tries the job gets the status `failed`. The web page will show it and offer a Retry button.
- The queue ignores a second add of a path that is already waiting.
- The clock is a parameter, so tests do not need to wait.

## TV client

- Library: `samsungtvws` (see Licenses). We use its art API: upload, select, list, delete.
- The first connection shows an Allow prompt on the TV. You approve it with the remote.
- The library saves a pairing token in a file. The service keeps that file in `config/token.txt`.
- Git ignores `config/local.toml` and `config/token.txt`. The token and the TV address never go into git.
- The exact method names can change between library versions. We will pin the version and check the names against the installed code before we write `tv.py`.

## Phone web app

The web app is the main way to add photos. It must work in Safari on iPhone and in Chrome on Android, with no app install.

- Upload one or more images, and choose crop or fit for each batch.
- The page is one screen with a large "Choose photos" button. It uses a file input that allows many files.
- On iPhone, a file input that lists `image/jpeg` and `image/png` makes Safari convert HEIC photos to JPEG before upload. A plain `image/*` input does not. We will list the types.
- The page shows a progress bar for each upload, then the state of each photo: preparing, waiting for the TV, on the TV, or failed.
- A second tab lists the artwork on the TV, with thumbnails and a Delete button.
- The page is mobile first: large touch targets, one column, no hover actions.
- Name lookup with `raspberrypi.local` works on iPhone and on most computers. It often fails on Android. The page therefore prints the Pi IP address and a QR code at startup, and the README tells you to give the Pi a fixed address on your router.
- Framework: Flask. It is small, well known, and runs well on a Pi. We will serve it with `waitress`, not the Flask development server.
- Upload limit: 25 MB per file. Phone photos are usually 2 to 8 MB.
- The server checks every upload with Pillow before it accepts the file. It never uses the file name from the phone. It makes its own.
- No login in version 1. Home network only. A shared PIN is a possible later addition.

## Ease of use

The main users can be in their sixties and not technical. These rules apply to every screen.

- Text starts at 17px and uses rem units. On iPhone the page follows the Dynamic Type text size. On Android, Chrome text scaling enlarges the page.
- The page is a web app that you add to the home screen. It has a manifest, an Apple touch icon, and an icon for Android. Settings shows the steps for iPhone and Android, and a QR code that opens the page on another phone. The server prints the same QR code in the terminal at startup.
- Words are plain. The page does not show pixel counts, zoom factors, or file names. A camera file name like `IMG_0193` becomes "Photo, Nov 9".
- A photo card scrolls like the rest of the page. To move the crop, you tap Adjust, drag, and tap Done.
- The Send button stays visible above the tab bar.
- Remove asks for confirmation, because it cannot be undone.
- In Activity, only the newest request that changed the screen says "Showing". Each row shows who and when.

## Choosing the photo that the TV shows

The TV shows one photo at a time. Two people can share the app, so a new upload never takes over the screen unless the person asks.

- The Add screen has a switch, "Show on the TV right away". It is off by default. In a batch, only the last photo gets the flag.
- In "On the TV", a person taps a photo and chooses "Show on TV". The request goes into the retry queue as a "show" job, so a TV that is off still gets it later.
- The last request wins. A new "show" job removes older waiting "show" jobs and clears `show_now` on waiting uploads.
- The `mark` table holds one row: which photo was chosen, by whom, and when. The name comes from a field in Settings and is kept in the phone. It is only a label, not a login.
- The TV decides which photo is current. A tile says "Showing" only when the TV reports it as current. A tile says "Chosen by" only when the mark matches.
- Samsung art can be chosen too. Only photos that Curator added can be removed.

## Watched folder

- An optional directory, for example a Samba share. A new image in it goes through the same flow as an upload.
- Processed files move to a `done/` subfolder, so they do not upload twice.
- Polling every few seconds is enough and avoids extra libraries.

## Risks

- The art API is not official. A Samsung update can break it. If that happens, upload fails until the library is updated.
- Art Mode works only when the TV is on the network. If the TV is fully off, the queue waits.
- The TV can show the Allow prompt again if the token is lost.

## Licenses

Checked on 2026-11-06.

| Package | Version | License | Note |
| --- | --- | --- | --- |
| `samsungtvws` (PyPI, GitHub `xchwarze/samsung-tv-ws-api`) | 3.0.7 | LGPL-3.0 | Active fork. Last push 2026-11-02. |
| `NickWaterton/samsung-tv-ws-api` | not used | LGPL-3.0 | Upstream of the fork. Last push 2026-10-28. |
| Pillow | 13.x | MIT-CMU (HPND) | Permissive. |

LGPL-3.0 lets a program use the library without being under the LGPL, if the program does not change the library and the user can replace it. We install it from PyPI as a normal dependency and do not copy or edit its code. This project is for private use. If you ever publish this project, keep the dependency separate and keep the LGPL notice. The PyPI metadata has an empty license field, so we took the license from the LICENSE file in the GitHub repository.

Pillow's license was not re-checked online in this session. Check it before you publish.
