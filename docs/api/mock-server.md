# MockSectraServer

```python
from sectra_client.mock_server import MockSectraServer
```

An in-memory Sectra PACS simulation for local development and testing. Exposes the same HTTP API as a real Sectra server, so your analysis app needs no code changes when switching between mock and production.

## Constructor

```python
MockSectraServer(
    api_version: str = "1.10",
    software_version: str = "4.2.0.0",
    token: str = "dev-token",
    slides: dict[str, ImageMetadata] | None = None,
    slide_files: dict[str, pathlib.Path | list[pathlib.Path]] | None = None,
)
```

| Parameter | Description |
|---|---|
| `token` | Auth token your analysis app must present |
| `slides` | Pre-populate slide metadata (keyed by slide ID) |
| `slide_files` | Pre-populate real WSI files to serve (keyed by slide ID) |

## Starting the server

Use `run()` as a context manager — it starts the server in a background thread and stops it on exit:

```python
mock = MockSectraServer(token="dev-token")
with mock.run(port=8001):
    # server is running at http://localhost:8001
    ...
# server is stopped
```

You can also call `start()` / `stop()` manually.

## Registering slides

```python
mock.add_slide(metadata: ImageMetadata) -> None
mock.add_slide_files(slide_id: str, files: pathlib.Path | list[pathlib.Path]) -> None
```

Use these before (or after) starting the server to register slide metadata and real WSI files. Auto-generated metadata is used for any slide ID not explicitly registered.

## Triggering invocations

```python
mock.trigger(webhook_url: str, invocation: Invocation) -> dict
```

Sends a fake invocation from the mock Sectra server to your app's webhook. Use this to drive an end-to-end test without clicking through a real PACS UI.

## Reading results

```python
mock.get_results(app_id: str, slide_id: str) -> list[ResultResponse]
```

Returns results stored in the mock server's memory — useful for asserting your app submitted the expected output.

## Full round-trip example

```python
import threading, time
import uvicorn
from sectra_client.mock_server import MockSectraServer
from sectra_client.schemas import CallbackInfo, CreateInvocation, WholeSlideInput

MOCK_PORT = 8001
APP_PORT  = 8000
SLIDE_ID  = "slide-001"

mock = MockSectraServer(token="dev-token")
with mock.run(port=MOCK_PORT):
    # Start your analysis app in the background
    app_config = uvicorn.Config(my_fastapi_app, host="localhost", port=APP_PORT, log_level="warning")
    app_server = uvicorn.Server(app_config)
    thread = threading.Thread(target=app_server.run, daemon=True)
    thread.start()
    time.sleep(1)  # wait for app to be ready

    # Fire a fake invocation
    mock.trigger(
        webhook_url=f"http://localhost:{APP_PORT}/sectra/hook",
        invocation=CreateInvocation(
            applicationId="my-app",
            slideId=SLIDE_ID,
            callbackInfo=CallbackInfo(
                url=f"http://localhost:{MOCK_PORT}",
                token="dev-token",
            ),
            cancellationToken="tok-001",
            input=WholeSlideInput(),
        ),
    )

    # Poll until the result arrives
    for _ in range(30):
        results = mock.get_results(app_id="my-app", slide_id=SLIDE_ID)
        if results:
            break
        time.sleep(1)

    print(results[0].displayResult)
```

See `examples/local_dev.py` in the repository for the complete, runnable version.

!!! note
    When connecting `SectraClient` to a `MockSectraServer`, pass `_allow_http=True` because the mock runs on plain HTTP.

    ```python
    SectraClient(url="http://localhost:8001", token="dev-token", _allow_http=True)
    ```
