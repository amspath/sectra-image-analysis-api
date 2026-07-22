"""Decide whether a slide is worth analysing, from an image notification alone.

Sectra sends a ``newImageFiles`` notification when new image files are imported. It
carries the slide's full (PHI-free) ``imageInfo``, so the triage decision needs no API
calls; and ignoring the notification is a valid response.

Image notifications do NOT arrive on the URL you registered. Sectra appends
``/imagenotification`` to it, so an app registered at ``/sectra/hook`` needs a second
route at ``/sectra/hook/imagenotification``.

Run it directly; it starts a mock Sectra server and an analysis app and fires two
notifications, one that gets accepted and one that gets skipped.

    python examples/image_notification.py
"""

import socket
import threading
import time

import uvicorn
from fastapi import FastAPI

from sectra_client.mock_server import MockSectraServer
from sectra_client.schemas import ImageMetadata, Invocation, NewImageFilesInvocation

analysis_app = FastAPI(title="Example Notification Triage App")

# Slides coarser than this aren't worth our time.
MAX_MICRONS_PER_PIXEL = 0.3


def _is_interesting(info: ImageMetadata) -> bool:
    """Decide whether to analyse, using only what the notification carried."""
    return info.micronsPerPixel <= MAX_MICRONS_PER_PIXEL and info.staining.displayName == "HE"


@analysis_app.post("/sectra/hook")
def sectra_hook(invocation: Invocation):
    """The registered URL: create / modify / cancel / delete land here."""
    # See local_dev.py for a full create -> download -> store round-trip.
    return {}


@analysis_app.post("/sectra/hook/imagenotification")
def sectra_image_notification(invocation: NewImageFilesInvocation):
    """The registered URL + /imagenotification: newImageFiles lands here."""
    info = invocation.imageInfo
    print(
        f"[analysis app] {invocation.slideId}: "
        f"{info.imageSize.width}x{info.imageSize.height}px, "
        f"{info.micronsPerPixel} um/px, staining={info.staining.displayName}"
    )

    if not _is_interesting(info):
        print("[analysis app]   -> not interesting, ignoring notification\n")
        return {}

    print("[analysis app]   -> interesting, would queue analysis here\n")
    # Fetch pixel data / files with SectraClient(invocation.callbackInfo.url, ...) and
    # store results, exactly as in local_dev.py.
    return {}


def _wait_for_server(server: uvicorn.Server, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Server did not start within 10 seconds")
        time.sleep(0.05)


def _slide(slide_id: str, microns_per_pixel: float, staining: str) -> ImageMetadata:
    """Minimal ImageMetadata differing only in the fields this example triages on."""
    return ImageMetadata(
        id=slide_id,
        isStreamable=True,
        imageSize={"width": 106624, "height": 77452},
        tileSize={"width": 240, "height": 240},
        micronsPerPixel=microns_per_pixel,
        focalPlanes=[{"id": "0", "offsetUm": 0.0}],
        opticalPaths=[{"id": "0", "description": "Brightfield"}],
        storedTileFormat={"mimeType": "image/jp2", "extension": "jp2"},
        availableTileFormats=[{"mimeType": "image/jpeg", "extension": "jpg"}],
        fileFormat={"mimeType": "application/dicom"},
        staining={"displayName": staining},
        block={"displayName": "Sentinel node"},
    )


if __name__ == "__main__":
    # Port 0 lets the OS pick a free port. 
    app_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    app_sock.bind(("localhost", 0))
    APP_PORT = app_sock.getsockname()[1]
    # The registered URL. notify() appends /imagenotification, as Sectra does.
    WEBHOOK = f"http://localhost:{APP_PORT}/sectra/hook"

    # Two slides: one we want, one we don't.
    mock = MockSectraServer(
        token="dev-token",
        slides={
            "slide-he": _slide("slide-he", microns_per_pixel=0.2465, staining="HE"),
            "slide-coarse": _slide("slide-coarse", microns_per_pixel=0.9, staining="HE"),
        },
    )

    with mock.run(port=0):
        app_config = uvicorn.Config(analysis_app, fd=app_sock.fileno(), log_level="warning")
        app_server = uvicorn.Server(app_config)
        threading.Thread(target=app_server.run, daemon=True).start()
        _wait_for_server(app_server)

        print(f"Mock Sectra server  : {mock.url}")
        print(f"Analysis app        : http://localhost:{APP_PORT}\n")

        # notify() builds the payload from the mock's own slide metadata, so the
        # notification always agrees with what GET /slides/{id}/info later returns.
        for slide_id in ("slide-he", "slide-coarse"):
            print(f"Notifying about new image files for {slide_id} ...")
            mock.notify(webhook_url=WEBHOOK, slide_id=slide_id)

        print("Done. Notifications for uninteresting slides cost zero API calls.")
