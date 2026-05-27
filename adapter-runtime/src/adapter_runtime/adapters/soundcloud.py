from adapter_runtime.adapters.yt_dlp_adapter import YtDlpAdapter


class SoundCloudAdapter(YtDlpAdapter):
	def __init__(self) -> None:
		super().__init__(
			name="soundcloud",
			url_patterns=[
				r"https?://(www\.)?soundcloud\.com/",
			],
		)
