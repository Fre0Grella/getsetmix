"""/metrics — Prometheus text exposition format."""
from __future__ import annotations

from .db import db


def render(active_downloads: int) -> str:
    s = db.stats()
    lines: list[str] = []

    def metric(name: str, help_: str, mtype: str, samples: list[tuple[str, float]]) -> None:
        lines.append(f"# HELP {name} {help_}")
        lines.append(f"# TYPE {name} {mtype}")
        for labels, value in samples:
            lines.append(f"{name}{labels} {value:g}")

    metric("getsetmix_jobs", "Job counts by status", "gauge",
           [('{status="%s"}' % k, v) for k, v in sorted(s["status_counts"].items())])
    metric("getsetmix_active_downloads", "Downloads currently in flight", "gauge",
           [("", active_downloads)])
    metric("getsetmix_download_duration_seconds_sum",
           "Total time spent downloading+ingesting", "counter",
           [("", s["download_seconds_sum"])])
    metric("getsetmix_download_duration_seconds_count",
           "Number of completed downloads measured", "counter",
           [("", s["download_seconds_count"])])
    metric("getsetmix_errors_total", "Download errors by source", "counter",
           [('{source="%s"}' % k, v) for k, v in sorted(s["errors_by_source"].items())])
    metric("getsetmix_songs_downloaded", "Songs downloaded per window", "gauge", [
        ('{window="30d"}', s["songs_30d"]),
        ('{window="365d"}', s["songs_365d"]),
        ('{window="all"}', s["songs_all_time"]),
    ])
    metric("getsetmix_healthy", "1 if the service is healthy", "gauge", [("", 1)])
    return "\n".join(lines) + "\n"
