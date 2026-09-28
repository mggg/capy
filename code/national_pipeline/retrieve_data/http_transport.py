"""Read provider responses and download files in small pieces instead of all at once."""

import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests
from tqdm import tqdm


class DataProviderError(Exception):
    """A provider error described without including URLs or responses that may contain keys."""


class RetryableDownloadError(DataProviderError):
    """A broken connection or incomplete transfer that can be retried with a fresh file."""


@contextmanager
def open_http_response(
    url: str, parameters: dict[str, str] | None = None, authorization: str | None = None
) -> Iterator[requests.Response]:
    """Open a successful provider response and keep it available inside a ``with`` block.

    HTTP status 200 means the provider accepted the request. The response is closed when the block
    ends, including when reading fails. This checks the connection and response status; the caller
    still needs to check whether the returned content is the expected data. HTTP 429 (too many
    requests) gets up to three retries. Retry-After sets the wait when valid; otherwise, waits are
    30, 60, and 120 seconds. Each rejected response is closed before waiting. Connection failures
    are passed to the file retrieval caller, which retries the whole transfer with a fresh
    temporary file. This context cannot restart a response already being read.

    Args:
        url (str): Address of the provider's data service or downloadable file.
        parameters (dict[str, str] | None): Request settings added to the URL, including an API
            key if needed. Defaults to None.
        authorization (str | None): API key or other value sent in the Authorization header.
            Defaults to None.

    Yields:
        requests.Response: Response whose data must be read before leaving the ``with`` block.

    Raises:
        RetryableDownloadError: A connection, timeout, or interrupted response needs a fresh
            attempt.
        DataProviderError: The status remains 429 after retries, the requested wait is too large
            for the system, another status is not 200, or the requests library reports a
            connection or reading error. Messages omit credentials.
    """
    headers = {"Accept-Encoding": "identity", "User-Agent": "capy replication data retrieval"}
    if authorization:
        headers["Authorization"] = authorization

    try:
        for attempt in range(4):
            with requests.get(
                url, params=parameters, headers=headers, stream=True, timeout=(30, 180)
            ) as response:
                if response.status_code == 200:
                    yield response
                    return

                if response.status_code != 429 or attempt == 3:
                    raise DataProviderError(f"Provider returned HTTP {response.status_code}")

                wait_seconds = get_rate_limit_wait_seconds(
                    response.headers.get("Retry-After"), retry_number=attempt + 1
                )

            tqdm.write(
                f"HTTP 429: waiting {wait_seconds:g} seconds before retry {attempt + 1}/3.",
                file=sys.stderr,
            )
            sys.stderr.flush()
            try:
                time.sleep(wait_seconds)
            except OverflowError:
                raise DataProviderError(
                    "Provider requested a retry delay too long to wait; rerun later"
                ) from None
    except requests.exceptions.SSLError as error:
        raise DataProviderError(f"Transport failed ({type(error).__name__})") from None
    except (
        requests.ConnectionError,
        requests.Timeout,
        requests.exceptions.ChunkedEncodingError,
    ) as error:
        raise RetryableDownloadError(f"Transport failed ({type(error).__name__})") from None
    except requests.RequestException as error:
        raise DataProviderError(f"Transport failed ({type(error).__name__})") from None


def get_rate_limit_wait_seconds(retry_after: str | None, retry_number: int) -> float:
    """Read the server's requested wait, or use a longer delay on each retry.

    Retry-After can contain seconds or an HTTP date. Past dates mean no wait is needed. See
    https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3.

    Args:
        retry_after (str | None): Response header, or None when absent.
        retry_number (int): Upcoming retry, starting at 1 and ending at 3.

    Returns:
        float: Seconds to wait. Missing or invalid headers use 30, 60, then 120 seconds.
    """
    fallback_seconds = 30 * 2 ** (retry_number - 1)
    if retry_after is None:
        return fallback_seconds

    try:
        if retry_after.strip().isascii() and retry_after.strip().isdigit():
            return float(int(retry_after))

        retry_date = parsedate_to_datetime(retry_after)
        if retry_date.tzinfo is None:
            retry_date = retry_date.replace(tzinfo=UTC)

        return max(0, retry_date.timestamp() - time.time())
    except (ValueError, TypeError, OverflowError):
        return fallback_seconds


def download_file(
    url: str,
    temporary_path: Path,
    authorization: str | None = None,
    *,
    parameters: dict[str, str] | None = None,
    download_label: str = "Download",
) -> None:
    """Download into a temporary file and check the byte count when the response allows it.

    The provider's Content-Length header gives the expected number of bytes. This is checked only
    when the header is present and the response is not compressed for transfer, since requests may
    decompress the data before writing it. File-format checks happen later. Terminals show a
    temporary byte counter with speed and, when the size is known, an ETA. Redirected output omits
    the bar. Labels never use provider URLs, which may contain secrets.

    Args:
        url (str): Address of the file to download.
        temporary_path (Path): Empty temporary file. The caller checks its contents and moves
            it to the final filename after this function returns.
        authorization (str | None): Optional Authorization header value. Defaults to None.
        parameters (dict[str, str] | None): Query settings, including an API key if needed.
            Defaults to None.
        download_label (str): Local filename or other safe progress label. Long labels are
            shortened from the left to leave room for byte counts and speed. Defaults to Download.

    Raises:
        RetryableDownloadError: The connection fails transiently or the byte count is incomplete.
        DataProviderError: The response status is not 200, a permanent connection error occurs, or
            Content-Length is invalid.
        OSError: Writing or inspecting the temporary file fails.
    """
    with open_http_response(url, parameters=parameters, authorization=authorization) as response:
        content_length_header = response.headers.get("Content-Length")
        content_encoding = response.headers.get("Content-Encoding", "identity")
        expected_byte_count = None
        if content_length_header is not None and content_encoding == "identity":
            try:
                expected_byte_count = int(content_length_header)
            except ValueError:
                raise DataProviderError(
                    "Provider returned an invalid Content-Length header"
                ) from None

        display_label = download_label
        if len(display_label) > 28:
            display_label = f"...{display_label[-25:]}"

        with (
            tqdm(
                total=expected_byte_count,
                desc=display_label,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                miniters=1,
                leave=False,
                dynamic_ncols=True,
                disable=None,
            ) as byte_progress,
            temporary_path.open("wb") as stream,
        ):
            for chunk in response.iter_content(1024 * 1024):
                stream.write(chunk)
                byte_progress.update(len(chunk))

        downloaded_bytes = temporary_path.stat().st_size
        if expected_byte_count is not None and expected_byte_count != downloaded_bytes:
            raise RetryableDownloadError("Downloaded byte count differs from Content-Length")
