from adapter_runtime.adapters.yt_dlp_adapter import YtDlpAdapter


class YouTubeAdapter(YtDlpAdapter):
    def __init__(self) -> None:
        super().__init__(
            name="youtube",
            url_patterns=[
                r"https?://(www\.)?youtube\.com/",
                r"https?://youtu\.be/",
            ],
        )
