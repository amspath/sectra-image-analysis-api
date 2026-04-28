# SectraClient

```python
from sectra_client import SectraClient
```

The primary interface for communicating with a Sectra PACS instance. Supports use as a context manager (recommended) or manually via `close()`.

## Constructor

```python
SectraClient(url: str, token: str, _allow_http: bool = False)
```

| Parameter | Description |
|---|---|
| `url` | Base URL of the Sectra Image Analysis API (from `callbackInfo.url`) |
| `token` | Auth token (from `callbackInfo.token`) |
| `_allow_http` | Whether to allow plain HTTP during communication with Sectra (useful for `MockSectraServer`) |

## Properties

| Property | Type | Description |
|---|---|---|
| `version_info` | `ApplicationInfo` | API and software version reported by the server |
| `response_headers` | `dict` | Headers to forward in your webhook response (required by Sectra) |

## Image metadata

### `get_image_metadata`

```python
client.get_image_metadata(slide_id: str, extended: bool = False, phi: bool = False) -> ImageMetadata
```

Retrieves slide metadata including dimensions, focal planes, optical paths, and staining info. Set `extended=True` for additional fields and `phi=True` to include protected health information.

### `get_image_infos_in_case`

```python
client.get_image_infos_in_case(
    accession_number: str,
    phi: bool = False,
    accession_number_issuer_id: str | None = None,
) -> list[CaseImageInfo]
```

Returns all slides belonging to a case, looked up by accession number. Requires IA-API 1.9+.

### `get_image_infos_in_case_by_slide_id`

```python
client.get_image_infos_in_case_by_slide_id(
    slide_id: str,
    phi: bool = False,
    accession_number_issuer_id: str | None = None,
) -> list[CaseImageInfo]
```

Same as above but resolves the case from a known `slide_id`. Requires IA-API 1.9+.

## File operations

### `get_label_image`

```python
client.get_label_image(slide_id: str) -> LabelImage
```

Retrieves the slide's label/thumbnail image. Call `.convert_to_pil()` on the result to get a Pillow `Image`.

### `download_slide_files`

```python
client.download_slide_files(slide_id: str, output_dir: pathlib.Path | str) -> list[pathlib.Path]
```

Downloads all WSI files for a slide into `output_dir` (created if absent). Returns the paths of the saved files. Handles multipart responses transparently.

## Results

### `create_results`

```python
client.create_results(app_id: str, results: Result) -> ResultResponse
```

Submits analysis results to Sectra. Returns the stored result including its assigned `id`.

### `get_result_by_result_id`

```python
client.get_result_by_result_id(app_id: str, result_id: int) -> ResultResponse
```

Fetches a single stored result by ID.

### `get_all_results`

```python
client.get_all_results(wsi_id: str, app_id: str) -> list[ResultResponse]
```

Returns all results stored for a slide/application pair.

### `update_results`

```python
client.update_results(app_id: str, result_id: int, result: AdaptedResult) -> ResultResponse
```

Updates an existing result. `AdaptedResult` requires the current `versionId` (optimistic concurrency).

## Quality control

### `set_quality_control`

```python
client.set_quality_control(slide_id: str, quality_control: QualityControl) -> None
```

Sets the QC status for a slide. Requires IA-API 1.10+.

## Errors

`SectraRequestError` is raised when Sectra returns a non-2xx response.

```python
from sectra_client.utils.errors import SectraRequestError

try:
    client.get_image_metadata(slide_id)
except SectraRequestError as e:
    print(e.status_code, e.path, e.text)
```

Failed requests are retried up to 5 times with exponential backoff on connection errors.
