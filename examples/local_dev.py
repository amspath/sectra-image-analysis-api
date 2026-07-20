import os
import pathlib
import threading
import time

import uvicorn
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import JSONResponse

from sectra_client.client import SectraClient
from sectra_client.mock_server import MockSectraServer
from sectra_client.schemas import (
    CallbackInfo,
    CreateInvocation,
    DisplayProperties,
    NewImageFilesInvocation,
    Point,
    Polygon,
    PrimitiveItem,
    Result,
    ResultData,
    Style,
    WholeSlideInput,
)
from sectra_client.schemas.invocation import Invocation
from sectra_client.schemas.results import PrimitiveResultContent

# ---------------------------------------------------------------------------
# Image analysis webhook app — replace this with your own logic
# ---------------------------------------------------------------------------

analysis_app = FastAPI(title="Example Analysis App")

# Directory where downloaded WSI files will be written
DOWNLOAD_DIR = pathlib.Path("./downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


def _run_analysis(invocation: Invocation) -> None:
    """Download slide files and store results. Runs after the webhook has responded."""
    with SectraClient(
        url=invocation.callbackInfo.url,
        token=invocation.callbackInfo.token,
        _allow_http=True,
    ) as client:
        # Download the WSI files for this slide
        downloaded = client.download_slide_files(
            slide_id=invocation.slideId,
            output_dir=DOWNLOAD_DIR / invocation.slideId,
        )
        print(f"[analysis app] Downloaded {len(downloaded)} file(s):")
        for p in downloaded:
            print(f"  {p}  ({p.stat().st_size} bytes)")

        # --- run your analysis here ---

        result_payload = Result(
            slideId=invocation.slideId,
            displayResult="Mock Analysis Complete",
            displayProperties=DisplayProperties({"Status": "OK", "Confidence": "99%"}),
            applicationVersion="0.0.1",
            data=ResultData(
                result=PrimitiveResultContent(
                    content=[
                        PrimitiveItem(
                            polygons=[
                                Polygon(
                                    points=[
                                        Point(x=0.1, y=0.1),
                                        Point(x=0.9, y=0.1),
                                        Point(x=0.9, y=0.9),
                                        Point(x=0.1, y=0.9),
                                    ]
                                )
                            ],
                            style=Style(strokeStyle="#00FF00", size=3),
                        )
                    ]
                )
            ),
        )

        # Call back to Sectra (the mock server) to store the permanent result.
        # _allow_http=True is needed because the mock server runs on plain HTTP.
        client.create_results(app_id=invocation.applicationId, results=result_payload)


@analysis_app.post("/sectra/hook")
def sectra_hook(invocation: Invocation, background_tasks: BackgroundTasks):
    """Receive an invocation from Sectra and post a result back.

    Returns a temporary empty result immediately so the caller is not blocked
    while the (potentially slow) analysis runs in the background.
    """
    # An image notification just says "new files arrived" — decide here whether the
    # slide is worth analysing at all. Ignoring it is a valid response.
    if isinstance(invocation, NewImageFilesInvocation):
        info = invocation.imageInfo
        print(
            f"[analysis app] Notified about {invocation.slideId}: "
            f"{info.imageSize.width}x{info.imageSize.height} @ {info.micronsPerPixel} um/px "
            f"— skipping."
        )
        return JSONResponse({})

    background_tasks.add_task(_run_analysis, invocation)

    # Return a temporary empty result — Sectra shows this while processing.
    empty = Result(
        slideId=invocation.slideId,
        displayResult="",
        applicationVersion="0.0.1",
        data=ResultData(result=PrimitiveResultContent(content=[])),
    )
    return JSONResponse(empty.model_dump())


# ---------------------------------------------------------------------------
# Entry point: run the full round-trip from a single Python script
# ---------------------------------------------------------------------------


def _wait_for_server(server: uvicorn.Server, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("Server did not start within 10 seconds")
        time.sleep(0.05)


if __name__ == "__main__":
    MOCK_PORT = 8001
    APP_PORT = 8000
    SLIDE_ID = "slide-001"

    # Point this at a real WSI file on your disk.
    WSI_FILE = pathlib.Path("/path/to/your/slide.tiff")

    # Start the mock Sectra server and register the WSI file for the slide.
    mock = MockSectraServer(
        token="dev-token",
        slide_files={SLIDE_ID: WSI_FILE},
    )
    with mock.run(port=MOCK_PORT):
        # Start the analysis app in a background thread
        app_config = uvicorn.Config(analysis_app, host="localhost", port=APP_PORT, log_level="warning")
        app_server = uvicorn.Server(app_config)
        app_thread = threading.Thread(target=app_server.run, daemon=True)
        app_thread.start()
        _wait_for_server(app_server)

        print(f"Mock Sectra server  : http://localhost:{MOCK_PORT}")
        print(f"Analysis app        : http://localhost:{APP_PORT}")
        print()

        # Notify the app that new image files arrived. The app inspects the metadata
        # and decides not to analyse, so nothing is stored.
        print(f"Notifying about new image files for {SLIDE_ID} ...")
        print(
            "Notification response: "
            f"{mock.notify(webhook_url=f'http://localhost:{APP_PORT}/sectra/hook', slide_id=SLIDE_ID)}"
        )
        print()

        # Trigger a fake CreateInvocation: mock Sectra → analysis app
        print(f"Triggering invocation for {SLIDE_ID} ...")
        response = mock.trigger(
            webhook_url=f"http://localhost:{APP_PORT}/sectra/hook",
            invocation=CreateInvocation(
                applicationId="my-app",
                slideId=SLIDE_ID,
                callbackInfo=CallbackInfo(
                    url=f"http://localhost:{MOCK_PORT}",
                    token="dev-token",
                ),
                cancellationToken="token-001",
                input=WholeSlideInput(),
            ),
        )
        print(f"Webhook response    : {response}")

        # The webhook returns immediately; wait for the background task to finish.
        print("Waiting for analysis to complete ...")
        deadline = time.monotonic() + 120
        results = []
        while time.monotonic() < deadline:
            results = mock.get_results(app_id="my-app", slide_id=SLIDE_ID)
            if results:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Analysis did not complete within 120 seconds")

        print(f"\nStored results ({len(results)} total):")
        for r in results:
            print(f"  id={r.id}  displayResult={r.displayResult!r}  displayProperties={r.displayProperties}")

        # Shut down analysis app
        app_server.should_exit = True
        app_thread.join(timeout=5)

    print("\nAll done — both servers stopped.")
