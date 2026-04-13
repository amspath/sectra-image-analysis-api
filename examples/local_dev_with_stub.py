"""Example: local development using StubSectraClient.

In production, swap StubSectraClient for SectraClient — no other changes needed
because both satisfy SectraClientProtocol.
"""
import logging

from sectra_client import SectraClientProtocol
from sectra_client.schemas import PrimitiveResultContent, Result, ResultData
from sectra_client.testing import StubSectraClient

logging.basicConfig(level=logging.INFO)


def run_analysis(client: SectraClientProtocol, app_id: str, slide_id: str) -> None:
    """Analyse a slide and post results back to Sectra."""
    meta = client.get_image_metadata(slide_id)
    print(f"Slide {meta.id}: {meta.imageSize.width}x{meta.imageSize.height}px "
          f"@ {meta.micronsPerPixel} µm/px")

    result = Result(
        slideId=slide_id,
        displayResult="Analysis complete",
        applicationVersion="1.0.0",
        data=ResultData(result=PrimitiveResultContent(content=[])),
    )
    response = client.create_results(app_id=app_id, results=result)
    print(f"Posted result id={response.id} versionId={response.versionId}")


# --- local dev: no server required ---
with StubSectraClient() as client:
    run_analysis(client, app_id="my-app", slide_id="slide-abc123")

# --- production: swap in the real client ---
# from sectra_client import SectraClient
# with SectraClient(url="https://sectra.example.com", token="<token>") as client:
#     run_analysis(client, app_id="my-app", slide_id="slide-abc123")
