from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class Metadata:
    title: str
    artist: str
    album: str = ""
    genre: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Metadata":
        title = str(data.get("title", "")).strip()
        artist = str(data.get("artist", "")).strip()
        if not title or not artist:
            raise ValueError("metadata requires title and artist")
        return cls(
            title=title,
            artist=artist,
            album=str(data.get("album", "")).strip(),
            genre=str(data.get("genre", "")).strip(),
        )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"title": self.title, "artist": self.artist}
        if self.album:
            out["album"] = self.album
        if self.genre:
            out["genre"] = self.genre
        return out


@dataclass(frozen=True)
class PreviewRequest:
    schema_version: int
    job_id: str
    source_url: str
    adapter_hint: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any], default_schema: int) -> "PreviewRequest":
        job_id = str(data.get("job_id", "")).strip()
        source_url = str(data.get("source_url", "")).strip()
        if not job_id:
            raise ValueError("job_id is required")
        if not source_url:
            raise ValueError("source_url is required")
        schema_version = int(data.get("schema_version") or default_schema)
        adapter_hint = data.get("adapter_hint")
        return cls(
            schema_version=schema_version,
            job_id=job_id,
            source_url=source_url,
            adapter_hint=str(adapter_hint).strip() if adapter_hint else None,
        )


@dataclass(frozen=True)
class PreviewResponse:
    schema_version: int
    job_id: str
    source_url: str
    metadata: Optional[Metadata] = None
    cover_url: Optional[str] = None
    cover_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "source_url": self.source_url,
        }
        if self.metadata is not None:
            out["metadata"] = self.metadata.to_dict()
        if self.cover_url:
            out["cover_url"] = self.cover_url
        if self.cover_path:
            out["cover_path"] = self.cover_path
        if self.error:
            out["error"] = self.error
        return out


@dataclass(frozen=True)
class DownloadRequest:
    schema_version: int
    job_id: str
    source_url: str
    adapter_hint: Optional[str]
    metadata: Metadata
    output_format: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any], default_schema: int) -> "DownloadRequest":
        job_id = str(data.get("job_id", "")).strip()
        source_url = str(data.get("source_url", "")).strip()
        if not job_id:
            raise ValueError("job_id is required")
        if not source_url:
            raise ValueError("source_url is required")
        schema_version = int(data.get("schema_version") or default_schema)
        adapter_hint = data.get("adapter_hint")
        metadata = Metadata.from_dict(data.get("metadata") or {})
        output_format = str(data.get("output_format", "")).strip()
        if not output_format:
            raise ValueError("output_format is required")
        return cls(
            schema_version=schema_version,
            job_id=job_id,
            source_url=source_url,
            adapter_hint=str(adapter_hint).strip() if adapter_hint else None,
            metadata=metadata,
            output_format=output_format,
        )


@dataclass(frozen=True)
class DownloadResponse:
    schema_version: int
    job_id: str
    source_url: str
    audio_path: Optional[str] = None
    cover_path: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "job_id": self.job_id,
            "source_url": self.source_url,
        }
        if self.audio_path:
            out["audio_path"] = self.audio_path
        if self.cover_path:
            out["cover_path"] = self.cover_path
        if self.error:
            out["error"] = self.error
        return out
