# Python Client for Sectra

This python package aims to facilite the development of AI applications for Sectra PACS.

## Installation

To install sectra_client:
```
pip install "sectra-image-analysis-api @ git+https://github.com/amspath/sectra-image-analysis-api.git"
```

## Usage

Before using the client, make sure you have access to a valid authentication token, and url, sent in the analysis requests.

### Example 1: Retrieve image information

```python
from sectra_client import SectraClient

# Info, sent by Sectra in the request
callback_url = "http://sectraweb.acc1.umcinfra.nl/SectraPathologyServer/external/imageanalysis/v1"
callback_token = "abcde"
slide_id = "fghij"

# Use the context manager
with SectraClient(
    url=callback_url,
    token=callback_token
) as client:
    # Returns the image info with extended and personal health information data
    image_info = client.get_image_metadata(slide_id, extended=True, phi=True)
```

### Example 2: Download WSI
```python
from sectra_client import SectraClient

# Info, sent by Sectra in the request
...

# Use the context manager
with SectraClient(
    url=callback_url,
    token=callback_token
) as client:
    # Download the file(s) to an output directory, and returns the file paths of the file(s). 
    file_paths = client.download_slide_files(slide_id, output_dir="./path/to/output/dir/")
```

### Example 3: Without context manager
It is also possible to use the SectraClient without the context manager
```python
from sectra_client import SectraClient

# Info, sent by Setra in the request
...

# Open context manager
client = SectraClient(url=callback_url, token=callback_token)

# Perform API interactions
image_info = client.get_image_metadata(slide_id, extended=True, phi=False)

# Make sure to close the connection
client.close()
```

### Example 4: Local development without a Sectra server

Use `StubSectraClient` as a drop-in replacement during local development. It keeps an in-memory store of results so that create, fetch, and update calls behave consistently within a session.

Type-hint your application code against `SectraClientProtocol` to make the swap seamless:

```python
from sectra_client import SectraClientProtocol
from sectra_client.schemas import PrimitiveResultContent, Result, ResultData
from sectra_client.testing import StubSectraClient


def run_analysis(client: SectraClientProtocol, app_id: str, slide_id: str) -> None:
    meta = client.get_image_metadata(slide_id)

    result = client.create_results(
        app_id=app_id,
        results=Result(
            slideId=slide_id,
            displayResult="Analysis complete",
            applicationVersion="1.0.0",
            data=ResultData(result=PrimitiveResultContent(content=[])),
        ),
    )
    print(f"Created result id={result.id}")


# Local dev — no server needed
with StubSectraClient() as client:
    run_analysis(client, app_id="my-app", slide_id="slide-123")

# Production — swap only the instantiation
# with SectraClient(url=callback_url, token=callback_token) as client:
#     run_analysis(client, app_id="my-app", slide_id="slide-123")
```

### Error handling and retries

Any request to the Sectra server is retried 5 times with exponential delays if there is a connection error. Any other error is not handled by the clients.

Clients raise `SectraRequestError` if the Sectra server returns an error status code (e.g., 400, 404, 500, etc.). The error includes the returned status code, text and the requested path.

