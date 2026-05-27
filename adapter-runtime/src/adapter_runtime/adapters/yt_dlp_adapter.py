import asyncio
import os
import re
from typing import Iterable, List, Tuple

from yt_dlp import YoutubeDL

from adapter_runtime.adapters.base import DownloadResult, PreviewResult


class YtDlpAdapter:
	def __init__(self, name: str, url_patterns: Iterable[str]) -> None:
		self.name = name
		self._patterns: List[re.Pattern[str]] = [re.compile(p) for p in url_patterns]

	def can_handle(self, source_url: str) -> bool:
		return any(pattern.search(source_url) for pattern in self._patterns)

	async def preview(self, source_url: str) -> PreviewResult:
		return await asyncio.to_thread(self._preview_sync, source_url)

	async def download(
		self,
		source_url: str,
		output_format: str,
		job_id: str,
		staging_dir: str,
	) -> DownloadResult:
		return await asyncio.to_thread(
			self._download_sync, source_url, output_format, job_id, staging_dir
		)

	def _preview_sync(self, source_url: str) -> PreviewResult:
		opts = {
			"quiet": True,
			"skip_download": True,
			"noplaylist": True,
		}
		with YoutubeDL(opts) as ydl:
			info = ydl.extract_info(source_url, download=False)
		if info.get("_type") == "playlist":
			raise ValueError("source collection requires expansion")

		title = str(info.get("title", "")).strip()
		artist = (
			str(info.get("artist", "")).strip()
			or str(info.get("uploader", "")).strip()
			or str(info.get("channel", "")).strip()
		)
		if not title or not artist:
			raise ValueError("adapter did not return title and artist")

		return PreviewResult(
			title=title,
			artist=artist,
			album=str(info.get("album", "") or "").strip(),
			genre=str(info.get("genre", "") or "").strip(),
			cover_url=str(info.get("thumbnail", "") or "").strip(),
		)

	def _download_sync(
		self,
		source_url: str,
		output_format: str,
		job_id: str,
		staging_dir: str,
	) -> DownloadResult:
		os.makedirs(staging_dir, exist_ok=True)
		outtmpl = os.path.join(staging_dir, f"{job_id}.%(ext)s")
		postprocessors, final_ext = self._postprocessors_for_format(output_format)

		opts = {
			"quiet": True,
			"outtmpl": outtmpl,
			"noplaylist": True,
		}
		if postprocessors:
			opts["postprocessors"] = postprocessors

		with YoutubeDL(opts) as ydl:
			info = ydl.extract_info(source_url, download=True)

		original_path = ydl.prepare_filename(info)
		audio_path = (
			self._replace_extension(original_path, final_ext)
			if final_ext
			else original_path
		)

		return DownloadResult(audio_path=audio_path)

	@staticmethod
	def _postprocessors_for_format(output_format: str) -> Tuple[List[dict], str]:
		normalized = output_format.lower()
		if normalized in {"mp3", "mp3-320"}:
			return (
				[
					{
						"key": "FFmpegExtractAudio",
						"preferredcodec": "mp3",
						"preferredquality": "320",
					}
				],
				"mp3",
			)
		if normalized == "flac":
			return (
				[
					{
						"key": "FFmpegExtractAudio",
						"preferredcodec": "flac",
					}
				],
				"flac",
			)
		return ([], "")

	@staticmethod
	def _replace_extension(path: str, ext: str) -> str:
		base, _ = os.path.splitext(path)
		return f"{base}.{ext}"
