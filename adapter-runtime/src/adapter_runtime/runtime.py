import asyncio
import json
import logging
from typing import Any, Dict

import nats

from adapter_runtime.adapters import SoundCloudAdapter, YouTubeAdapter
from adapter_runtime.config import Config
from adapter_runtime.models import (
	DownloadRequest,
	DownloadResponse,
	Metadata,
	PreviewRequest,
	PreviewResponse,
)
from adapter_runtime.registry import AdapterRegistry

logger = logging.getLogger("adapter_runtime")


class AdapterRuntime:
	def __init__(
		self,
		registry: AdapterRegistry,
		schema_version: int,
		staging_dir: str,
	) -> None:
		self._registry = registry
		self._schema_version = schema_version
		self._staging_dir = staging_dir

	async def handle_preview(self, payload: Dict[str, Any]) -> Dict[str, Any]:
		job_id = str(payload.get("job_id", "")).strip()
		source_url = str(payload.get("source_url", "")).strip()
		schema_version = int(payload.get("schema_version") or self._schema_version)

		try:
			req = PreviewRequest.from_dict(payload, self._schema_version)
			adapter = self._registry.resolve(req.source_url, req.adapter_hint)
			result = await adapter.preview(req.source_url)
			response = PreviewResponse(
				schema_version=req.schema_version,
				job_id=req.job_id,
				source_url=req.source_url,
				metadata=Metadata(
					title=result.title,
					artist=result.artist,
					album=result.album,
					genre=result.genre,
				),
				cover_url=result.cover_url or None,
				cover_path=result.cover_path or None,
			)
			return response.to_dict()
		except Exception as exc:  # noqa: BLE001 - surface adapter errors as response payloads
			logger.exception("preview failed")
			response = PreviewResponse(
				schema_version=schema_version,
				job_id=job_id,
				source_url=source_url,
				error=str(exc),
			)
			return response.to_dict()

	async def handle_download(self, payload: Dict[str, Any]) -> Dict[str, Any]:
		job_id = str(payload.get("job_id", "")).strip()
		source_url = str(payload.get("source_url", "")).strip()
		schema_version = int(payload.get("schema_version") or self._schema_version)

		try:
			req = DownloadRequest.from_dict(payload, self._schema_version)
			adapter = self._registry.resolve(req.source_url, req.adapter_hint)
			result = await adapter.download(
				req.source_url,
				req.output_format,
				req.job_id,
				self._staging_dir,
			)
			response = DownloadResponse(
				schema_version=req.schema_version,
				job_id=req.job_id,
				source_url=req.source_url,
				audio_path=result.audio_path,
				cover_path=result.cover_path or None,
			)
			return response.to_dict()
		except Exception as exc:  # noqa: BLE001 - surface adapter errors as response payloads
			logger.exception("download failed")
			response = DownloadResponse(
				schema_version=schema_version,
				job_id=job_id,
				source_url=source_url,
				error=str(exc),
			)
			return response.to_dict()


def create_default_registry() -> AdapterRegistry:
	return AdapterRegistry([YouTubeAdapter(), SoundCloudAdapter()])


async def serve_forever(config: Config) -> None:
	logging.basicConfig(level=logging.INFO, format="%(message)s")
	nc = await nats.connect(config.nats_url)

	runtime = AdapterRuntime(
		registry=create_default_registry(),
		schema_version=config.schema_version,
		staging_dir=config.staging_dir,
	)

	async def handle_preview(msg) -> None:
		payload = json.loads(msg.data.decode("utf-8"))
		response = await runtime.handle_preview(payload)
		await msg.respond(json.dumps(response).encode("utf-8"))

	async def handle_download(msg) -> None:
		payload = json.loads(msg.data.decode("utf-8"))
		response = await runtime.handle_download(payload)
		await msg.respond(json.dumps(response).encode("utf-8"))

	await nc.subscribe(config.preview_subject, cb=handle_preview)
	await nc.subscribe(config.download_subject, cb=handle_download)

	logger.info("adapter runtime ready")
	try:
		while True:
			await asyncio.sleep(3600)
	finally:
		await nc.drain()


def run() -> None:
	config = Config.from_env()
	asyncio.run(serve_forever(config))
