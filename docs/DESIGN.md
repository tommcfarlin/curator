# Design: Curator

## Goal

A small service on a Raspberry Pi. You upload your own images from a phone or computer. The service sends them to the Art Mode of a Samsung The Frame over the home network. You do not need a Samsung Art Store subscription.

The TV is a 2021 The Frame, model QN55LS03AAFXZA, Tizen 6.0, at 192.168.1.20.

## Status

This is the first deliverable. The image resize module and the retry queue exist and have tests. The TV client, the web page, the folder watcher and the service entry point are not written yet. Nothing in this project has connected to the TV or to the Pi.

## Parts

| Part | File | Status |
| --- | --- | --- |
| Image resize and crop | `curator/imaging.py` | done, tested |
| Retry queue (SQLite) | `curator/queue.py` | done, tested |
| Settings and token loader | `curator/config.py` | planned |
| TV client (art API) | `curator/tv.py` | planned |
| Worker loop | `curator/worker.py` | planned |
| Web page and API | `curator/web.py` | planned |
| Folder watcher | `curator/watch.py` | planned |
| Entry point | `curator/__main__.py` | planned |

## Decisions (2026-11-06)

- The "On the TV" tab lists all art on the TV, including Samsung art. Curator can show any piece. Curator can delete only photos that it uploaded. It keeps a record of the content IDs that it uploaded, and it checks that record before every delete.
- Version 1 has no mat. Photos fill the screen.
- There is no login. Anyone on the home Wi-Fi can open the page.
- Version 1 has no rotation timer. The photo that you pick is the photo that stays on the screen. A rotation timer is a future item (GitHub milestone "Future State").
- Open question: how the art API marks Samsung art and uploaded photos. We will check this on the TV with the installed library before we write the list code.

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

## Retry queue

- The queue is a SQLite file. It is in the Python standard library, so it adds no dependency.
- The delay doubles after each failure: 30 s, 60 s, 120 s, up to 1 hour.
- After 12 failed tries the job gets the status `failed`. The web page will show it and offer a Retry button.
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
