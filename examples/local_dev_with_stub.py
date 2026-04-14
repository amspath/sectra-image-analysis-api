"""Example: local development using StubSectraClient.

In production, swap StubSectraClient for SectraClient — no other changes needed
because both satisfy SectraClientProtocol.
"""
import logging

from sectra_client import SectraClientProtocol
from sectra_client.schemas import AdaptedResult, PrimitiveResultContent, Result, ResultData
from sectra_client.testing import StubSectraClient

logging.basicConfig(level=logging.INFO)


def run_analysis(client: SectraClientProtocol, app_id: str, slide_id: str) -> None:
    """Analyse a slide and post results back to Sectra."""
    meta = client.get_image_metadata(slide_id)
    print(f"Slide {meta.id}: {meta.imageSize.width}x{meta.imageSize.height}px "
          f"@ {meta.micronsPerPixel} µm/px")

    # Create an initial result
    result = client.create_results(
        app_id=app_id,
        results=Result(
            slideId=slide_id,
            displayResult="Analysis complete",
            applicationVersion="1.0.0",
            data=ResultData(result=PrimitiveResultContent(content=[])),
        ),
    )
    print(f"Created result id={result.id} versionId={result.versionId}")

    # Fetch it back by ID to confirm round-trip
    fetched = client.get_result_by_result_id(app_id=app_id, result_id=result.id)
    print(f"Fetched result id={fetched.id} displayResult={fetched.displayResult!r}")

    # Update it
    updated = client.update_results(
        app_id=app_id,
        result_id=result.id,
        result=AdaptedResult(
            slideId=slide_id,
            displayResult="Analysis complete (revised)",
            applicationVersion="1.0.0",
            versionId=result.versionId,
            data=result.data,
        ),
    )
    print(f"Updated result id={updated.id} displayResult={updated.displayResult!r}")

    # List all results for the slide
    all_results = client.get_all_results(wsi_id=slide_id, app_id=app_id)
    print(f"Total results for slide: {len(all_results)}")


# --- local dev: no server required ---
with StubSectraClient() as client:
    run_analysis(client, app_id="my-app", slide_id="slide-abc123")
    run_analysis(client, app_id="my-app", slide_id="slide-def456")
    print(f"\nAll results across both slides: {len(client.get_all_results('slide-abc123', 'my-app'))} + "
          f"{len(client.get_all_results('slide-def456', 'my-app'))}")

# --- production: swap in the real client ---
# from sectra_client import SectraClient
# with SectraClient(url="https://sectra.example.com", token="<token>") as client:
#     run_analysis(client, app_id="my-app", slide_id="slide-abc123")
