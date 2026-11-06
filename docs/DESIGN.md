# Design: Frame Art Pi

## Goal

A small service on a Raspberry Pi. You upload your own images from a phone or computer. The service sends them to the Art Mode of a Samsung The Frame over the home network. You do not need a Samsung Art Store subscription.

The TV is a 2021 The Frame, model QN55LS03AAFXZA, Tizen 6.0, at 192.168.1.20.

## Status

This is the first deliverable. The image resize module and the retry queue exist and have tests. The TV client, the web page, the folder watcher and the service entry point are not written yet. Nothing in this project has connected to the TV or to the Pi.

## Parts

| Part | File | Status |
| --- | --- | --- |
| Image resize and crop | `frameart/imaging.py` | done, tested |
| Retry queue (SQLite) | `frameart/queue.py` | done, tested |
| Settings and token loader | `frameart/config.py` | planned |
| TV client (art API) | `frameart/tv.py` | planned |
| Worker loop | `frameart/worker.py` | planned |
| Web page and API | `frameart/web.py` | planned |
| Folder watcher | `frameart/watch.py` | planned |
| Entry point | `frameart/__main__.py` | planned |

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

## Web page

- Served by the Pi, for example `http://raspberrypi.local:8080`.
- Upload one or more images. Choose crop or fit.
- List the artwork on the TV, with thumbnails. Delete a piece.
- Show the queue state: pending, done, failed.
- There is no login. The service is for a home network only. Do not expose port 8080 to the internet.

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
