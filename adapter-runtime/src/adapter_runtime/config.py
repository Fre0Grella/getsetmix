from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Config:
    nats_url: str
    preview_subject: str
    download_subject: str
    schema_version: int
    staging_dir: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            nats_url=os.getenv("GSM_NATS_URL", "nats://localhost:4222"),
            preview_subject=os.getenv("GSM_ADAPTER_PREVIEW_SUBJECT", "adapter.preview"),
            download_subject=os.getenv(
                "GSM_ADAPTER_DOWNLOAD_SUBJECT", "adapter.download"
            ),
            schema_version=int(os.getenv("GSM_ADAPTER_SCHEMA_VERSION", "1")),
            staging_dir=os.getenv("GSM_ADAPTER_STAGING_DIR", "/cache/staging"),
        )
