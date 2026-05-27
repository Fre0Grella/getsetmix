import asyncio
import logging
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from adapter_runtime.adapters.base import DownloadResult, PreviewResult  # noqa: E402
from adapter_runtime.registry import AdapterRegistry  # noqa: E402
from adapter_runtime.runtime import AdapterRuntime  # noqa: E402


class FakeAdapter:
    name = "fake"

    def __init__(self, can_handle: bool = True, fail_download: bool = False) -> None:
        self._can_handle = can_handle
        self._fail_download = fail_download

    def can_handle(self, source_url: str) -> bool:
        return self._can_handle

    async def preview(self, source_url: str) -> PreviewResult:
        return PreviewResult(
            title="Title",
            artist="Artist",
            album="Album",
            genre="Genre",
            cover_url="https://img.test/cover.jpg",
            cover_path="C:\\cache\\cover.jpg",
        )

    async def download(
        self, source_url: str, output_format: str, job_id: str, staging_dir: str
    ) -> DownloadResult:
        if self._fail_download:
            raise ValueError("adapter failed")
        return DownloadResult(
            audio_path="C:\\cache\\track.mp3", cover_path="C:\\cache\\cover.jpg"
        )


class AdapterRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        logger = logging.getLogger("adapter_runtime")
        logger.handlers = [logging.NullHandler()]
        logger.propagate = False
        logger.setLevel(logging.CRITICAL)

    def test_preview_roundtrip(self) -> None:
        runtime = AdapterRuntime(
            registry=AdapterRegistry([FakeAdapter()]),
            schema_version=1,
            staging_dir="C:\\cache",
        )

        payload = {
            "schema_version": 1,
            "job_id": "job-1",
            "source_url": "https://example.test/track/1",
        }

        response = asyncio.run(runtime.handle_preview(payload))
        self.assertEqual(response["job_id"], "job-1")
        self.assertEqual(response["metadata"]["title"], "Title")
        self.assertEqual(response["metadata"]["artist"], "Artist")
        self.assertEqual(response["cover_url"], "https://img.test/cover.jpg")

    def test_download_roundtrip(self) -> None:
        runtime = AdapterRuntime(
            registry=AdapterRegistry([FakeAdapter()]),
            schema_version=1,
            staging_dir="C:\\cache",
        )

        payload = {
            "schema_version": 1,
            "job_id": "job-2",
            "source_url": "https://example.test/track/2",
            "metadata": {"title": "T", "artist": "A"},
            "output_format": "mp3-320",
        }

        response = asyncio.run(runtime.handle_download(payload))
        self.assertEqual(response["audio_path"], "C:\\cache\\track.mp3")
        self.assertEqual(response["cover_path"], "C:\\cache\\cover.jpg")

    def test_download_error_propagates(self) -> None:
        runtime = AdapterRuntime(
            registry=AdapterRegistry([FakeAdapter(fail_download=True)]),
            schema_version=1,
            staging_dir="C:\\cache",
        )

        payload = {
            "schema_version": 1,
            "job_id": "job-3",
            "source_url": "https://example.test/track/3",
            "metadata": {"title": "T", "artist": "A"},
            "output_format": "mp3-320",
        }

        response = asyncio.run(runtime.handle_download(payload))
        self.assertIn("error", response)
        self.assertEqual(response["error"], "adapter failed")


if __name__ == "__main__":
    unittest.main()
