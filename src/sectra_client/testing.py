"""Stub SectraClient for local development without a real Sectra server."""
from types import TracebackType
import logging
import pathlib
from typing import Optional

from sectra_client.schemas import (
    AdaptedResult,
    ApplicationInfo,
    CaseImageInfo,
    DisplayedName,
    ImageMetadata,
    QualityControl,
    Result,
    ResultResponse,
    Size,
    SlideFormat,
    TileFormat,
)
from sectra_client.schemas.image import LabelImage

log = logging.getLogger(__name__)

_STUB_VERSION_ID = "stub-version-1"
_STUB_APP_VERSION = "stub-1.0.0"
# Minimal valid JPEG (SOI + EOI markers only)
_STUB_JPEG = b"\xff\xd8\xff\xd9"


class StubSectraClient:
    """Drop-in stub for SectraClient. Returns plausible fake data and logs all calls.

    Keeps an in-memory store of results so that create/get/update are consistent
    within a session. IDs are auto-incremented per (app_id, slide_id) pair.

    Intended for local development and testing without a real Sectra server.
    Satisfies SectraClientProtocol structurally, so it can be used anywhere
    the real SectraClient is accepted.

    Example::

        from sectra_client.testing import StubSectraClient

        with StubSectraClient() as client:
            meta = client.get_image_metadata("my-slide-id")
    """

    def __init__(self, url: str = "stub://localhost", token: str = "stub-token") -> None:
        log.info("[SECTRA STUB] init url=%s", url)
        self.version_info = ApplicationInfo(apiVersion="1.10", softwareVersion="stub")
        # {(app_id, result_id): ResultResponse}
        self._results: dict[tuple[str, int], ResultResponse] = {}
        self._next_id: int = 1

    def __enter__(self) -> "StubSectraClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def close(self) -> None:
        log.info("[SECTRA STUB] close")

    # -- internal helpers --------------------------------------------------

    def _stub_case_image(self, slide_id: str) -> CaseImageInfo:
        return CaseImageInfo(
            id=slide_id,
            staining=DisplayedName(displayName="HE"),
            block=DisplayedName(displayName="A1"),
        )

    def _make_response(self, result_id: int, source: Result, version_id: str) -> ResultResponse:
        return ResultResponse(
            id=result_id,
            versionId=version_id,
            slideId=source.slideId,
            displayResult=source.displayResult,
            applicationVersion=source.applicationVersion,
            attachments=source.attachments,
            data=source.data,
            displayProperties=source.displayProperties,
        )

    # -- public API --------------------------------------------------------

    def get_image_infos_in_case(
        self,
        accession_number: str,
        phi: bool = False,
        accession_number_issuer_id: Optional[str] = None,
    ) -> list[CaseImageInfo]:
        log.info("[SECTRA STUB] get_image_infos_in_case accession_number=%s", accession_number)
        return [self._stub_case_image(f"stub-slide-{accession_number}")]

    def get_image_infos_in_case_by_slide_id(
        self,
        slide_id: str,
        phi: bool = False,
        accession_number_issuer_id: Optional[str] = None,
    ) -> list[CaseImageInfo]:
        log.info("[SECTRA STUB] get_image_infos_in_case_by_slide_id slide_id=%s", slide_id)
        return [self._stub_case_image(slide_id)]

    def get_image_metadata(
        self, slide_id: str, extended: bool = False, phi: bool = False
    ) -> ImageMetadata:
        log.info("[SECTRA STUB] get_image_metadata slide_id=%s", slide_id)
        fmt = TileFormat(mimeType="image/jpeg", extension="jpg")
        return ImageMetadata(
            id=slide_id,
            isStreamable=True,
            imageSize=Size(width=100000, height=80000),
            tileSize=Size(width=256, height=256),
            micronsPerPixel=0.25,
            focalPlanes=[],
            opticalPaths=[],
            storedTileFormat=fmt,
            availableTileFormats=[fmt],
            fileFormat=SlideFormat(mimeType="image/svs"),
            staining=DisplayedName(displayName="HE"),
            block=DisplayedName(displayName="A1"),
        )

    def get_label_image(self, slide_id: str) -> LabelImage:
        log.info("[SECTRA STUB] get_label_image slide_id=%s", slide_id)
        return LabelImage(image=_STUB_JPEG)

    def download_slide_files(
        self, slide_id: str, output_dir: pathlib.Path | str
    ) -> list[pathlib.Path]:
        log.info("[SECTRA STUB] download_slide_files slide_id=%s", slide_id)
        return []

    def create_results(self, app_id: str, results: Result) -> ResultResponse:
        result_id = self._next_id
        self._next_id += 1
        response = self._make_response(result_id, results, version_id=f"stub-version-{result_id}")
        self._results[(app_id, result_id)] = response
        log.info(
            "[SECTRA STUB] create_results app_id=%s slideId=%s -> id=%d",
            app_id, results.slideId, result_id,
        )
        return response

    def get_result_by_result_id(self, app_id: str, result_id: int) -> ResultResponse:
        log.info("[SECTRA STUB] get_result_by_result_id app_id=%s result_id=%d", app_id, result_id)
        return self._results[(app_id, result_id)]

    def get_all_results(self, wsi_id: str, app_id: str) -> list[ResultResponse]:
        log.info("[SECTRA STUB] get_all_results wsi_id=%s app_id=%s", wsi_id, app_id)
        return [
            r for (aid, _), r in self._results.items()
            if aid == app_id and r.slideId == wsi_id
        ]

    def update_results(self, app_id: str, result_id: int, result: AdaptedResult) -> ResultResponse:
        response = self._make_response(result_id, result, version_id=result.versionId)
        self._results[(app_id, result_id)] = response
        log.info(
            "[SECTRA STUB] update_results app_id=%s result_id=%d slideId=%s",
            app_id, result_id, result.slideId,
        )
        return response

    def set_quality_control(self, slide_id: str, quality_control: QualityControl) -> None:
        log.info(
            "[SECTRA STUB] set_quality_control slide_id=%s status=%s",
            slide_id,
            quality_control.qualityControl.status,
        )
