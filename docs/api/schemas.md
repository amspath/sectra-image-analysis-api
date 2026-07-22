# Schemas

All models are Pydantic `BaseModel` subclasses. Import from `sectra_client.schemas`:

```python
from sectra_client.schemas import Point, Polygon, Result, ...
```

---

## Common

| Model | Fields | Notes |
|---|---|---|
| `Point` | `x: float`, `y: float` | Normalized coordinates (0–1) |
| `Polygon` | `points: list[Point]` | Closed shape |
| `Polyline` | `points: list[Point]` | Open path |
| `Size` | `width: int`, `height: int` | Pixel dimensions |
| `CallbackInfo` | `url: str`, `token: str` | Sectra callback credentials, from the invocation |
| `ApplicationInfo` | `apiVersion: str`, `softwareVersion: str` | Reported by the server |

---

## Image

### `ImageMetadata`
Full slide metadata: pixel size, tile format, focal planes, optical paths, staining, and more. Returned by `SectraClient.get_image_metadata()`.

### `CaseImageInfo`
Lightweight summary of a slide within a case. Returned by `get_image_infos_in_case*()`.

### `LabelImage`
```python
label: LabelImage = client.get_label_image(slide_id)
pil_image = label.convert_to_pil()
```

---

## Invocation

Sectra POSTs an `Invocation` to your webhook. It is a **discriminated union** on the `action` field.

```python
from sectra_client.schemas.invocation import Invocation

@app.post("/sectra/hook")
def hook(invocation: Invocation):
    match invocation:
        case CreateInvocation():          ...
        case ModifyInvocation():          ...
        case CancelInvocation():          ...
        case DeleteInvocation():          ...
        case NewImageFilesInvocation():   ...
```

| Type | `action` | Key extra fields |
|---|---|---|
| `CreateInvocation` | `CREATE` | `input: CreateInput` |
| `ModifyInvocation` | `MODIFY` | `input: ResultResponse` (existing result to update) |
| `CancelInvocation` | `CANCEL` | — |
| `DeleteInvocation` | `DELETE` | `input: ResultResponse` (result to delete) |
| `NewImageFilesInvocation` | `NEW_IMAGE_FILES` | `imageInfo: ImageMetadata` |

All invocations share: `applicationId`, `slideId`, `callbackInfo`.

### `CreateInput`

Another discriminated union on `type`:

| Type | `type` | Extra fields |
|---|---|---|
| `WholeSlideInput` | `WHOLE_SLIDE` | — |
| `TaggedPolygonInput` | `TAGGED_POLYGON` | `content: TaggedPolygonContent` |
| `MultiAreaInput` | `MULTI_AREA` | `content: MultiAreaContent` |

### Image notifications

`NewImageFilesInvocation` (`action: "newImageFiles"`) is sent when new image files are imported for a slide, so your app can decide whether the slide is worth analysing. Unlike the other four actions it carries the slide's full `imageInfo` (PHI-free) up front, so the decision needs no API calls.

It does **not** arrive on the URL you registered. Sectra appends `/imagenotification` to it:

| Action | Delivered to |
|---|---|
| `create` / `modify` / `cancel` / `delete` | the registered URL, e.g. `/sectra/hook` |
| `newImageFiles` | `<registered URL>/imagenotification` |

So an app needs a second route. Without it, notifications 404 silently.

```python
@app.post("/sectra/hook")
def hook(invocation: Invocation):
    ...                        # create / modify / cancel / delete


@app.post("/sectra/hook/imagenotification")
def image_notification(invocation: NewImageFilesInvocation):
    if invocation.imageInfo.micronsPerPixel > 0.5:
        return {}              # too low-res for us — ignore
    ...                        # otherwise queue the analysis
```

To simulate one in local development, use [`MockSectraServer.notify()`](mock-server.md): it builds the payload from the mock's own slide metadata, so the notification always agrees with what the mock later serves.

Pass the registered URL — `notify()` appends `/imagenotification` itself, just like Sectra.

```python
mock.notify(webhook_url="http://localhost:8000/sectra/hook", slide_id="slide-001")
```

See `examples/image_notification.py` for a runnable end-to-end triage example.

---

## Results

### Building a result

```python
Result(
    slideId=...,
    displayResult="Human-readable label",
    displayProperties=DisplayProperties({"Key": "Value"}),
    applicationVersion="1.0.0",
    data=ResultData(result=<PrimitiveResultContent or PatchResultContent>),
)
```

### `PrimitiveResultContent`

A list of drawable items (polygons, polylines, labels).

```python
PrimitiveResultContent(
    content=[
        PrimitiveItem(
            polygons=[Polygon(points=[...])],
            style=Style(strokeStyle="#FF0000", size=2, fillStyle="#FF000033"),
        )
    ]
)
```

| Model | Key fields |
|---|---|
| `PrimitiveItem` | `polygons`, `polylines`, `labels`, `style` |
| `Style` | `strokeStyle: str` (CSS color), `fillStyle: str`, `size: int` |
| `Label` | `text: str`, `position: Point` |

### `PatchResultContent`

A grid of classified patches over the slide.

```python
PatchResultContent(
    content=PatchContent(
        patches=[Patch(tag=2, position=Point(x=0.5, y=0.5), sortKeyValue=0.9)],
        tags=["Negative", "Uncertain", "Positive"],
        patchSize=128,
        magnification=2.0,
        ...
    )
)
```

| Model | Key fields |
|---|---|
| `PatchContent` | `patches`, `tags`, `polygons`, `actions`, `patchSize`, `magnification`, `statuses` |
| `Patch` | `tag: int`, `position: Point`, `sortKeyValue: float` |
| `Action` | `id`, `name`, `tooltip`, `state` |
| `Status` | `value: bool`, `message: str` |

### `ResultResponse`

Returned by `create_results()` and `get_*results*()`. Extends `Result` with:

| Field | Type | Description |
|---|---|---|
| `id` | `int` | Assigned result ID |
| `versionId` | `str` | Required for updates (optimistic concurrency) |

### `AdaptedResult`

Used with `update_results()`. Same fields as `Result`, plus `versionId: str`.

---

## Quality control

```python
from sectra_client.schemas import QualityControl, QualityControlData, QualityControlStatus

client.set_quality_control(
    slide_id,
    QualityControl(
        applicationVersion="1.0.0",
        qualityControl=QualityControlData(
            status=QualityControlStatus.QUALITY_OK,
            versionId=current_version_id,
        ),
    ),
)
```

| `QualityControlStatus` | Value |
|---|---|
| `NOT_SET` | Default, no decision |
| `QUALITY_OK` | Slide accepted |
| `REJECTED` | Slide rejected |
