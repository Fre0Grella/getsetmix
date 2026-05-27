from typing import Iterable, Optional

from adapter_runtime.adapters.base import Adapter


class AdapterRegistry:
	def __init__(self, adapters: Iterable[Adapter]) -> None:
		self._adapters = list(adapters)
		self._by_name = {adapter.name: adapter for adapter in self._adapters}

	def resolve(self, source_url: str, adapter_hint: Optional[str]) -> Adapter:
		if adapter_hint:
			adapter = self._by_name.get(adapter_hint)
			if adapter is not None:
				return adapter
			raise ValueError(f"unknown adapter_hint: {adapter_hint}")

		for adapter in self._adapters:
			if adapter.can_handle(source_url):
				return adapter
		raise ValueError("unsupported source URL")
