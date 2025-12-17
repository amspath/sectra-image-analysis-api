import logging
import pathlib
import re
from typing import List, Optional, cast
from urllib.parse import urlsplit, urlunsplit

import requests
from requests_toolbelt.multipart import decoder

from sectra_client.schemas import (
    AdaptedResult,
    ApplicationInfo,
    CaseImageInfo,
    ImageMetadata,
    QualityControl,
    Result,
    ResultResponse,
)
from sectra_client.schemas.image import LabelImage
from sectra_client.utils.errors import SectraRequestError
from sectra_client.utils.helpers import JSONPayload, connection_retry

logger = logging.getLogger(__name__)


class SectraClient:
    __slots__ = ("_url", "_token", "version_info", "_headers", "_session")

    def __init__(self, url: str, token: str) -> None:
        # Normalize base url
        parts = urlsplit(url.strip())

        scheme = parts.scheme
        if scheme == "http" or scheme == "":
            scheme = "https"

        base = urlunsplit((scheme, parts.netloc, parts.path.rstrip("/"), parts.query, parts.fragment))
        self._url = base

        self._token = token
        self._headers = {"Authorization": f"Bearer {token}"}

        self._session = requests.Session()
        self._session.headers.update(self._headers)

        self.version_info = self._retrieve_version_info()

    def __enter__(self) -> "SectraClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        # Make sure to close the session
        self._session.close()

    @connection_retry()
    def _get(self, path: str, **kwargs) -> JSONPayload:
        url = f"{self._url}{path}"
        resp = self._session.get(url, params=kwargs)  # headers already on session
        if resp.status_code != 200:
            raise SectraRequestError(resp.status_code, resp.text, path)
        return resp.json()

    @connection_retry()
    def _get_raw(self, path: str, **kwargs) -> requests.Response:
        url = f"{self._url}{path}"
        resp = self._session.get(url, params=kwargs)
        if resp.status_code != 200:
            raise SectraRequestError(resp.status_code, resp.text, path)
        return resp

    @connection_retry()
    def _post(self, path: str, payload: JSONPayload, parse_response: bool = True) -> Optional[JSONPayload]:
        url = f"{self._url}{path}"
        resp = self._session.post(url, json=payload)
        if resp.status_code != 201:
            raise SectraRequestError(resp.status_code, resp.text, path)
        if parse_response:
            return resp.json()
        return None

    @connection_retry()
    def _put(self, path: str, values: JSONPayload, parse_response: bool = True) -> Optional[JSONPayload]:
        url = f"{self._url}{path}"
        resp = self._session.put(url, json=values)
        if resp.status_code != 200:
            raise SectraRequestError(resp.status_code, resp.text, path)
        if parse_response:
            return resp.json()
        return None

    def _retrieve_version_info(self) -> ApplicationInfo:
        """Retrieves the versions of DPAT from the server."""

        versions = ApplicationInfo(**cast(dict, self._get("/info")))
        self._headers.update(
            {"X-Sectra-ApiVersion": versions.apiVersion, "X-Sectra-SoftwareVersion": versions.softwareVersion}
        )
        self._session.headers.update(
            {"X-Sectra-ApiVersion": versions.apiVersion, "X-Sectra-SoftwareVersion": versions.softwareVersion}
        )
        return versions

    def close(self) -> None:
        """Closes the SectraClient session."""
        self._session.close()

    def get_image_infos_in_case(
        self, accession_number: str, phi: bool = False, accession_number_issuer_id: Optional[str] = None
    ) -> list[CaseImageInfo]:
        """Retrieves all slides in a case. Available from IA-API 1.9 (Sectra 4.1).

        Args:
            accession_number (str): Accession number of the case
            phi (bool): Whether Protected Health Information should be included or not.
                Defaults to False.
            accession_number_issuer_id (Optional[str]): Issuer ID of the accession number.
                Defaults to None.
        Returns:
            list[CaseImageInfo]: List of slides in the case

        """
        path = f"/requests/{accession_number}/images/info"
        params: dict[str, str] = {}
        if phi:
            params["includePHI"] = "true"
        if accession_number_issuer_id:
            params["accessionNumberIssuerId"] = accession_number_issuer_id
        return [CaseImageInfo(**img) for img in cast(list[dict], self._get(path, **params))]

    def get_image_infos_in_case_by_slide_id(
        self, slide_id: str, phi: bool = False, accession_number_issuer_id: Optional[str] = None
    ) -> list[CaseImageInfo]:
        """Retrieves all slides in the case a slide belongs to. Available from IA-API 1.9 (Sectra 4.1).

        Args:
            slide_id (str): Id of the slide
            phi (bool): Whether Protected Health Information should be included or not.
                Defaults to False.
            accession_number_issuer_id (Optional[str]): Issuer ID of the accession number.
                Defaults to None.
        Returns:
            list[CaseImageInfo]: List of slides in the case

        """
        path = f"/slides/{slide_id}/request/images/info"
        params: dict[str, str] = {}
        if phi:
            params["includePHI"] = "true"
        if accession_number_issuer_id:
            params["accessionNumberIssuerId"] = accession_number_issuer_id
        return [CaseImageInfo(**img) for img in cast(list[dict], self._get(path, **params))]

    def get_image_metadata(self, slide_id: str, extended: bool = False, phi: bool = False) -> ImageMetadata:
        """Retrieves a slide metadata from its slide_id.

        Args:
            slide_id (str): Id of the slide to retrieve info from
            extended (bool): Whether extended info should be included or not.
                Defaults to False.
            phi (bool): Whether Protected Health Information should be included or not.
                Defaults to False.

        Returns:
            ImageMetadata: Requested slide info
        """
        path = f"/slides/{slide_id}/info"
        params: dict[str, str] = {}
        if extended:
            params["scope"] = "extended"
        if phi:
            params["includePHI"] = "true"
        return ImageMetadata(**cast(dict, self._get(path, **params)))

    def get_label_image(self, slide_id: str) -> LabelImage:
        """Retrieves the label image for a slide.

        Args:
            slide_id (str): Id of the slide to retrieve the label image for
        Returns:
            LabelImage: Label image data
        """
        path = f"/slides/{slide_id}/label"
        resp = self._get_raw(path)
        return LabelImage(image=resp.content)

    def download_slide_files(self, slide_id: str, output_dir: pathlib.Path | str) -> list[pathlib.Path]:
        """Download and store all files associated with a slide.

        This calls `/slides/{slide_id}/files`, decodes the multipart response,
        and writes each part to disk. Filenames are taken from the
        Content-Disposition header when available; otherwise a fallback name
        is generated.

        Args:
            slide_id: Id of the slide to download files for.
            output_dir: Directory where files will be stored. Created if needed.

        Returns:
            List of paths to the written files.
        """
        path = f"/slides/{slide_id}/files"
        resp = self._get_raw(path)

        multipart_data = decoder.MultipartDecoder.from_response(resp)

        output_path = pathlib.Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        written_files: list[pathlib.Path] = []

        api_version = resp.headers.get("X-Sectra-ApiVersion", "unknown")

        for i, part in enumerate(multipart_data.parts):
            # Decode headers to text and normalise keys
            headers = {k.decode().lower(): v.decode() for k, v in part.headers.items()}
            disp = headers.get("content-disposition", "")

            # Try to extract filename from Content-Disposition
            m = re.search(r'filename="([^"]+)"', disp)
            if m:
                filename = m.group(1)
            else:
                raise AttributeError(
                    "Missing filename in Content-Disposition header for slide",
                    f"{slide_id} part {i} (API version: {api_version})",
                )

            file_path = output_path / filename

            with file_path.open("wb") as f:
                f.write(part.content)

            logger.info("Wrote slide file: %s", file_path)
            written_files.append(file_path)

        return written_files

    def create_results(self, app_id: str, results: Result) -> ResultResponse:
        """Creates a result in Sectra.

        Args:
            results (Result): Results payload

        Returns:
            ResultResponse: Parsed Sectra response.
        """
        path = f"/applications/{app_id}/results"
        resp = self._post(path, results.model_dump())
        return ResultResponse(**cast(dict, resp))

    def get_result_by_result_id(self, app_id: str, result_id: int) -> ResultResponse:
        """Retrieves a result by its result id.

        Args:
            app_id (str): Application id
            result_id (str): Result id
        Returns:
            ResultResponse: Retrieved result.
        """
        path = f"/applications/{app_id}/results/{result_id}"
        resp = self._get(path)
        return ResultResponse(**cast(dict, resp))

    def get_all_results(self, wsi_id: str, app_id: str) -> List[ResultResponse]:
        """Retrieves results.

        Args:
            wsi_id (str): Results id
            app_id (str): Application id
        Returns:
            ResultResponse: Retrieved results.
        """
        path = f"/applications/{app_id}/results/slide/{wsi_id}"
        resp = self._get(path)
        return [ResultResponse(**cast(dict, r)) for r in cast(list[dict], resp)]

    def update_results(self, app_id: str, result_id: int, result: AdaptedResult) -> ResultResponse:
        """Update existing results.

        Args:
            app_id (str): Application id
            result_id (int): Result id
            result (AdaptedResult): Updated result data

        Returns:
            ResultResponse: Updated results
        """
        path = f"/applications/{app_id}/results/{result_id}"
        resp = self._put(path, result.model_dump())
        return ResultResponse(**cast(dict, resp))

    def set_quality_control(self, slide_id: str, quality_control: QualityControl) -> None:
        """Sets quality control for a slide. Available from IA-API 1.10 (Sectra 4.2).

        Args:
            slide_id (str): Id of the slide to set quality control for
            quality_control (QualityControl): Quality control data to set

        Raises:
            DPATRequestError: If the request fails
        """
        path = f"/slides/{slide_id}/qualityControl"
        self._put(path, quality_control.model_dump(), parse_response=False)
