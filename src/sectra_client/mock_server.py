from __future__ import annotations

import io
import pathlib
import socket
import threading
import time
import uuid
from collections import defaultdict
from typing import Optional

import requests as _requests
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse, StreamingResponse
from PIL import Image

from sectra_client.schemas.common import CallbackInfo, DisplayedName, Size
from sectra_client.schemas.image import (
    CaseImageInfo,
    FocalPlane,
    ImageMetadata,
    OpticalPath,
    SlideFormat,
    TileFormat,
)
from sectra_client.schemas.info import ApplicationInfo
from sectra_client.schemas.invocation import Invocation, NewImageFilesInvocation
from sectra_client.schemas.quality_control import QualityControl, QualityControlData
from sectra_client.schemas.results import AdaptedResult, Result, ResultResponse

# ---------------------------------------------------------------------------
# Helpers for generating fake slide data
# ---------------------------------------------------------------------------


def _make_fake_metadata(slide_id: str) -> ImageMetadata:
    """Return plausible ImageMetadata for an unknown slide ID."""
    return ImageMetadata(
        id=slide_id,
        isStreamable=True,
        imageSize=Size(width=100_000, height=80_000),
        tileSize=Size(width=256, height=256),
        micronsPerPixel=0.25,
        focalPlanes=[FocalPlane(id="0", offsetUm=0.0)],
        opticalPaths=[OpticalPath(id="0", description="Brightfield")],
        storedTileFormat=TileFormat(mimeType="image/jpeg", extension="jpg"),
        availableTileFormats=[TileFormat(mimeType="image/jpeg", extension="jpg")],
        fileFormat=SlideFormat(mimeType="image/tiff"),
        staining=DisplayedName(displayName="HE"),
        block=DisplayedName(displayName="A1"),
    )


def _make_1x1_jpeg() -> bytes:
    """Return a minimal 1×1 white JPEG."""
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="JPEG")
    return buf.getvalue()


_LABEL_JPEG: bytes = _make_1x1_jpeg()


def _iter_multipart(boundary: str, paths: list[pathlib.Path]):
    """Yield multipart body chunks for a list of file paths without loading them into memory."""
    for path in paths:
        file_size = path.stat().st_size
        sent = 0
        start = time.monotonic()
        header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: attachment; filename="{path.name}"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode()
        yield header
        with path.open("rb") as f:
            while chunk := f.read(8 * 1024 * 1024):  # 8 MB chunks
                yield chunk
                sent += len(chunk)
                pct = sent * 100 // file_size if file_size else 100
                elapsed = time.monotonic() - start
                print(
                    f"\r[mock] Sending {path.name}: "
                    f"{sent / 1_048_576:.1f} / {file_size / 1_048_576:.1f} MB ({pct}%) "
                    f"[{elapsed:.1f}s]",
                    end="",
                    flush=True,
                )
        elapsed = time.monotonic() - start
        print(f"  done in {elapsed:.1f}s")  # newline after each file completes
        yield b"\r\n"
    yield f"--{boundary}--\r\n".encode()


# ---------------------------------------------------------------------------
# MockSectraServer
# ---------------------------------------------------------------------------


class MockSectraServer:
    """In-memory mock of the Sectra PACS Image Analysis API.

    Holds all state (slides, results, quality-control data) in Python dicts so
    tests and dev scripts can read back what was stored without going through
    HTTP.

    Parameters
    ----------
    api_version:
        Reported as ``ApplicationInfo.apiVersion`` on ``GET /info``.
    software_version:
        Reported as ``ApplicationInfo.softwareVersion`` on ``GET /info``.
    token:
        Bearer token that clients must supply.  Defaults to ``"dev-token"``.
    slides:
        Optional mapping of slide_id → ImageMetadata to pre-register.  Any
        slide_id not in this mapping will receive auto-generated fake metadata.
    slide_files:
        Optional mapping of slide_id → file path(s) to pre-register for
        ``GET /slides/{id}/files``.  Equivalent to calling
        :meth:`add_slide_files` for each entry after construction.
    """

    def __init__(
        self,
        api_version: str = "1.10",
        software_version: str = "4.2.0.0",
        token: str = "dev-token",
        slides: Optional[dict[str, ImageMetadata]] = None,
        slide_files: Optional[dict[str, pathlib.Path | list[pathlib.Path]]] = None,
    ) -> None:
        self.api_version = api_version
        self.software_version = software_version
        self.token = token

        self._slides: dict[str, ImageMetadata] = dict(slides) if slides else {}
        # slide_id → list of file paths served by GET /slides/{id}/files
        self._slide_files: dict[str, list[pathlib.Path]] = {}
        if slide_files:
            for sid, files in slide_files.items():
                self.add_slide_files(sid, files)
        # (app_id, result_id) → ResultResponse
        self._results: dict[tuple[str, int], ResultResponse] = {}
        self._result_counters: dict[str, int] = defaultdict(int)
        self._quality_controls: dict[str, QualityControlData] = {}

        self._host: str = "localhost"
        self._port: int = 8001
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None

    @property
    def port(self) -> int:
        """Port the server is bound to.

        Only meaningful once :meth:`start` has run. When started with ``port=0`` this
        is the port the OS actually assigned, not ``0``.
        """
        return self._port

    @property
    def url(self) -> str:
        """Base URL of this server, e.g. ``"http://localhost:8001"``."""
        return f"http://{self._host}:{self._port}"

    # ------------------------------------------------------------------
    # In-process state helpers (no HTTP needed)
    # ------------------------------------------------------------------

    def add_slide(self, metadata: ImageMetadata) -> None:
        """Pre-register a slide so the mock returns your custom metadata."""
        self._slides[metadata.id] = metadata

    def add_slide_files(
        self,
        slide_id: str,
        files: pathlib.Path | list[pathlib.Path],
    ) -> None:
        """Register real files to be served by ``GET /slides/{slide_id}/files``.

        When not set, the endpoint returns a minimal dummy TIFF.

        Parameters
        ----------
        slide_id:
            Slide to associate the files with.
        files:
            One or more file paths.  Each file is served as a separate
            multipart part, with the filename taken from ``path.name``.
        """
        if isinstance(files, pathlib.Path):
            files = [files]
        self._slide_files[slide_id] = list(files)

    def get_results(self, app_id: str, slide_id: str) -> list[ResultResponse]:
        """Return all stored results for *app_id* + *slide_id* (in-process).

        Reads directly from internal state — no HTTP round-trip required.
        """
        return [r for (aid, _), r in self._results.items() if aid == app_id and r.slideId == slide_id]

    def trigger(
        self,
        webhook_url: str,
        invocation: Invocation,
    ) -> dict:
        """Fire an invocation at *webhook_url*, simulating Sectra.

        Parameters
        ----------
        webhook_url:
            Full URL of the analysis app's invocation endpoint, e.g.
            ``"http://localhost:8000/sectra/hook"``.
        invocation:
            The invocation to fire.
        
        Returns
        -------
        dict
            JSON body returned by the webhook.
        """
        self._get_or_create_slide(invocation.slideId)  # ensure slide metadata exists for the invocation
        resp = _requests.post(webhook_url, json=invocation.model_dump(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def notify(
        self,
        webhook_url: str,
        slide_id: str,
        application_id: str = "my-app",
    ) -> dict:
        """Fire a ``newImageFiles`` image notification at *webhook_url*.

        Sectra does not deliver image notifications to the registered URL itself; it
        appends ``/imagenotification`` to it. So does this method — pass the same
        registered URL you pass to :meth:`trigger`.

        ``imageInfo`` is taken from this server's own slide metadata (registered via
        :meth:`add_slide`, or fabricated on demand), so the notification always agrees
        with what ``GET /slides/{slide_id}/info`` will subsequently return.

        Parameters
        ----------
        webhook_url:
            The app's *registered* URL, e.g. ``"http://localhost:8000/sectra/hook"``.
            The notification is POSTed to ``<webhook_url>/imagenotification``.
        slide_id:
            Slide that new image files were imported for.
        application_id:
            Application the notification is addressed to.

        Returns
        -------
        dict
            JSON body returned by the webhook.
        """
        invocation = NewImageFilesInvocation(
            applicationId=application_id,
            slideId=slide_id,
            callbackInfo=CallbackInfo(url=self.url, token=self.token),
            cancellationToken=str(uuid.uuid4()),
            imageInfo=self._get_or_create_slide(slide_id),
        )
        url = f"{webhook_url.rstrip('/')}/imagenotification"
        resp = _requests.post(url, json=invocation.model_dump(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def run(self, port: int = 8001, host: str = "localhost") -> "MockSectraServer":
        """Start the HTTP server in a background thread and return *self*.

        Designed for use as a context manager::

            with server.run(port=8001):
                ...  # server running here
            # server stopped on exit

        Or call :meth:`start` / :meth:`stop` directly for manual control.
        """
        self._host = host
        self._port = port
        self.start()
        return self

    def start(self) -> None:
        """Start the uvicorn server in a background daemon thread."""
        if self._server is not None:
            raise RuntimeError("Server is already running")

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_MAXSEG, 1440)
        except OSError as e:
            print(f"[mock] Warning: could not set TCP_MAXSEG: {e}")
        sock.bind((self._host, self._port))
        self._port = sock.getsockname()[1]
        self._sock = sock  # keep reference so GC doesn't close it

        config = uvicorn.Config(
            self.create_app(),
            fd=sock.fileno(),
            log_level="warning",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()

        deadline = time.monotonic() + 10.0
        while not self._server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("Mock server did not start within 10 seconds")
            time.sleep(0.05)

    def stop(self) -> None:
        """Shut down the background server."""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._server = None
        self._thread = None
        if self._sock is not None:
            self._sock.close()
            self._sock = None

    def __enter__(self) -> "MockSectraServer":
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    # ------------------------------------------------------------------
    # FastAPI application factory
    # ------------------------------------------------------------------

    def _get_or_create_slide(self, slide_id: str) -> ImageMetadata:
        if slide_id not in self._slides:
            self._slides[slide_id] = _make_fake_metadata(slide_id)
        return self._slides[slide_id]

    def _verify_token(self, authorization: Optional[str]) -> None:
        if authorization != f"Bearer {self.token}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    def create_app(self) -> FastAPI:
        """Build and return the FastAPI application.

        All Sectra endpoints plus a ``GET /dev/slides`` diagnostic route are
        registered.  The app captures ``self`` via closure so multiple server
        instances are independent.
        """
        app = FastAPI(
            title="Mock Sectra PACS Server",
            description="Local-dev mock of the Sectra Image Analysis API.",
        )

        # ---- /info --------------------------------------------------------
        @app.get("/info")
        def get_info(authorization: Optional[str] = Header(None)):
            self._verify_token(authorization)
            return ApplicationInfo(
                apiVersion=self.api_version,
                softwareVersion=self.software_version,
            ).model_dump()

        # ---- /slides/{slide_id}/info --------------------------------------
        @app.get("/slides/{slide_id}/info")
        def get_slide_info(slide_id: str, authorization: Optional[str] = Header(None)):
            self._verify_token(authorization)
            return self._get_or_create_slide(slide_id).model_dump()

        # ---- /slides/{slide_id}/label -------------------------------------
        @app.get("/slides/{slide_id}/label")
        def get_slide_label(slide_id: str, authorization: Optional[str] = Header(None)):
            self._verify_token(authorization)
            return Response(content=_LABEL_JPEG, media_type="image/jpeg")

        # ---- /slides/{slide_id}/files -------------------------------------
        @app.get("/slides/{slide_id}/files")
        def get_slide_files(slide_id: str, authorization: Optional[str] = Header(None)):
            self._verify_token(authorization)
            boundary = "mock_boundary"

            if slide_id in self._slide_files:
                # Stream the registered real files as multipart parts so large
                # WSI files are never loaded into memory all at once.
                return StreamingResponse(
                    _iter_multipart(boundary, self._slide_files[slide_id]),
                    media_type=f"multipart/form-data; boundary={boundary}",
                    headers={"X-Sectra-ApiVersion": self.api_version},
                )
            else:
                # Fall back to a minimal dummy TIFF (little-endian magic bytes)
                dummy_content = b"II\x2a\x00\x08\x00\x00\x00"
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: attachment; filename="{slide_id}.tiff"\r\n'
                    "Content-Type: image/tiff\r\n\r\n"
                ).encode() + dummy_content + f"\r\n--{boundary}--\r\n".encode()
                return Response(
                    content=body,
                    media_type=f"multipart/form-data; boundary={boundary}",
                    headers={"X-Sectra-ApiVersion": self.api_version},
                )

        # ---- /requests/{accession_number}/images/info --------------------
        @app.get("/requests/{accession_number}/images/info")
        def get_case_images_by_accession(accession_number: str, authorization: Optional[str] = Header(None)):
            self._verify_token(authorization)
            matching = [
                CaseImageInfo(
                    id=s.id,
                    staining=s.staining,
                    block=s.block,
                    specimen=s.specimen,
                    seriesInstanceUid=s.seriesInstanceUid,
                    lisSlideId=s.lisSlideId,
                )
                for s in self._slides.values()
                if s.accessionNumber == accession_number
            ]
            return [m.model_dump() for m in matching]

        # ---- /slides/{slide_id}/request/images/info ----------------------
        @app.get("/slides/{slide_id}/request/images/info")
        def get_case_images_by_slide(slide_id: str, authorization: Optional[str] = Header(None)):
            self._verify_token(authorization)
            meta = self._get_or_create_slide(slide_id)
            if meta.accessionNumber:
                siblings = [s for s in self._slides.values() if s.accessionNumber == meta.accessionNumber]
            else:
                siblings = [meta]
            result = [
                CaseImageInfo(
                    id=s.id,
                    staining=s.staining,
                    block=s.block,
                    specimen=s.specimen,
                    seriesInstanceUid=s.seriesInstanceUid,
                    lisSlideId=s.lisSlideId,
                )
                for s in siblings
            ]
            return [r.model_dump() for r in result]

        # ---- POST /applications/{app_id}/results -------------------------
        @app.post("/applications/{app_id}/results", status_code=201)
        def create_result(app_id: str, result: Result, authorization: Optional[str] = Header(None)):
            self._verify_token(authorization)
            self._result_counters[app_id] += 1
            result_id = self._result_counters[app_id]
            response = ResultResponse(**result.model_dump(), id=result_id, versionId=str(uuid.uuid4()))
            self._results[(app_id, result_id)] = response
            return JSONResponse(response.model_dump(), status_code=201)

        # ---- GET /applications/{app_id}/results/slide/{wsi_id} -----------
        # Registered before /{result_id} so the literal "slide" segment is
        # not mistakenly captured as an integer result_id.
        @app.get("/applications/{app_id}/results/slide/{wsi_id}")
        def get_results_for_slide(app_id: str, wsi_id: str, authorization: Optional[str] = Header(None)):
            self._verify_token(authorization)
            results = [r for (aid, _), r in self._results.items() if aid == app_id and r.slideId == wsi_id]
            return [r.model_dump() for r in results]

        # ---- GET /applications/{app_id}/results/{result_id} --------------
        @app.get("/applications/{app_id}/results/{result_id}")
        def get_result(app_id: str, result_id: int, authorization: Optional[str] = Header(None)):
            self._verify_token(authorization)
            key = (app_id, result_id)
            if key not in self._results:
                raise HTTPException(status_code=404, detail=f"Result {result_id} not found for app {app_id!r}")
            return self._results[key].model_dump()

        # ---- PUT /applications/{app_id}/results/{result_id} --------------
        @app.put("/applications/{app_id}/results/{result_id}")
        def update_result(
            app_id: str,
            result_id: int,
            result: AdaptedResult,
            authorization: Optional[str] = Header(None),
        ):
            self._verify_token(authorization)
            key = (app_id, result_id)
            if key not in self._results:
                raise HTTPException(status_code=404, detail=f"Result {result_id} not found for app {app_id!r}")
            data = result.model_dump()
            data["id"] = result_id
            data["versionId"] = str(uuid.uuid4())
            updated = ResultResponse(**data)
            self._results[key] = updated
            return updated.model_dump()

        # ---- PUT /slides/{slide_id}/qualityControl -----------------------
        @app.put("/slides/{slide_id}/qualityControl")
        def set_quality_control(
            slide_id: str,
            qc: QualityControl,
            authorization: Optional[str] = Header(None),
        ):
            self._verify_token(authorization)
            self._get_or_create_slide(slide_id)
            self._quality_controls[slide_id] = qc.qualityControl
            return Response(status_code=200)

        # ---- GET /dev/slides — diagnostic, no auth -----------------------
        @app.get("/dev/slides")
        def dev_list_slides():
            """List all registered slide IDs (for debugging)."""
            return list(self._slides.keys())

        return app


# ---------------------------------------------------------------------------
# Module-level default instance — used by: uvicorn sectra_client.mock_server:app
# ---------------------------------------------------------------------------
_default_server = MockSectraServer()
app = _default_server.create_app()
