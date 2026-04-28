# Quick Start

The `url` and `token` your app needs come from the invocation Sectra sends to your webhook — see `callbackInfo` in the [Invocation schema](api/schemas.md#invocation).

## Retrieve image metadata

```python
from sectra_client import SectraClient

with SectraClient(url=callback_url, token=callback_token) as client:
    metadata = client.get_image_metadata(slide_id, extended=True, phi=True)
    print(metadata.size)  # Size(width=..., height=...)
```

`extended=True` adds extra slide info; `phi=True` includes protected health information.

## Download WSI files

```python
from sectra_client import SectraClient

with SectraClient(url=callback_url, token=callback_token) as client:
    paths = client.download_slide_files(slide_id, output_dir="./downloads/")
    # paths is a list[pathlib.Path] of the saved files
```

## Submit results

```python
from sectra_client import SectraClient
from sectra_client.schemas import (
    DisplayProperties, Point, Polygon, PrimitiveItem,
    Result, ResultData, Style,
)
from sectra_client.schemas.results import PrimitiveResultContent

result = Result(
    slideId=slide_id,
    displayResult="Analysis complete",
    displayProperties=DisplayProperties({"Confidence": "95%"}),
    applicationVersion="1.0.0",
    data=ResultData(
        result=PrimitiveResultContent(
            content=[
                PrimitiveItem(
                    polygons=[Polygon(points=[
                        Point(x=0.0, y=0.0), Point(x=1.0, y=0.0),
                        Point(x=1.0, y=1.0), Point(x=0.0, y=1.0),
                    ])],
                    style=Style(strokeStyle="#FF0000", size=2),
                )
            ]
        )
    ),
)

with SectraClient(url=callback_url, token=callback_token) as client:
    response = client.create_results(app_id=application_id, results=result)
    # response.id is the assigned result ID
```

## Handling invocations with FastAPI

A minimal webhook that returns a temporary result immediately and runs analysis in the background:

```python
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import JSONResponse

from sectra_client import SectraClient
from sectra_client.schemas import Result, ResultData, Invocation, PrimitiveResultContent, CreateInvocation

app = FastAPI()
@app.post("/sectra/hook")
def hook(invocation: Invocation, background_tasks: BackgroundTasks):
    background_tasks.add_task(run_analysis, invocation)
    # Return an empty result immediately so Sectra isn't blocked
    if isinstance(invocation, CreateInvocation)
    with SectraClient(
        url=invocation.callbackInfo.url,
        token=invocation.callbackInfo.token,
    ) as client:
        metadata = client.get_image_metadata(invocation.slideId)
        # ... create some annotation ...
        create_response = client.create_results(invocation.applicationId, build_result(invocation.slideId))
        return JSONResponse(create_response.model_dump(), headers=client.response_headers)
```

## Local development with MockSectraServer

Use `MockSectraServer` to develop without a real Sectra instance. See [`MockSectraServer`](api/mock-server.md) for full details and a complete round-trip example.

```python
from sectra_client.mock_server import MockSectraServer

mock = MockSectraServer(token="dev-token")
with mock.run(port=8001):
    mock.trigger(
        webhook_url="http://localhost:8000/sectra/hook",
        invocation=...,
    )
    results = mock.get_results(app_id="my-app", slide_id="slide-001")
```
