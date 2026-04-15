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

## Local development with the mock server
`MockSectraServer` simulates a Sectra PACS instance in memory so you can develop and test without a real server.

```python
from sectra_client.mock_server import MockSectraServer

server = MockSectraServer(token="dev-token")
with server.run(port=8001):
    server.trigger(
        webhook_url="http://localhost:8000/sectra/hook",
        application_id="my-app",
        slide_id="slide-001",
    )
    results = server.get_results(app_id="my-app", slide_id="slide-001")
```

See `examples/local_dev.py` for a complete round-trip: both servers started from a single script, a fake invocation fired, and results read back.
