from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PreviewResult:
	title: str
	artist: str
	album: str = ""
	genre: str = ""
	cover_url: str = ""
	cover_path: str = ""


@dataclass(frozen=True)
class DownloadResult:
	audio_path: str
	cover_path: str = ""


class Adapter(Protocol):
	name: str

	def can_handle(self, source_url: str) -> bool:
		...

	async def preview(self, source_url: str) -> PreviewResult:
		...

	async def download(
		self,
		source_url: str,
		output_format: str,
		job_id: str,
		staging_dir: str,
	) -> DownloadResult:
		...
