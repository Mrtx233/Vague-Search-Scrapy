import json
import os
from typing import Any, Dict, Iterable, List, Set


def _safe_load_json(path: str, default: Any):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


class JsonSetStore:
    """
    简单的本地 JSON 集合存储，用于去重（如关键词、MD5 等）
    """

    def __init__(self, path: str):
        self.path = path
        self._data: Set[str] = set()
        self._load()

    def _load(self) -> None:
        raw = _safe_load_json(self.path, [])
        if isinstance(raw, dict):
            raw = raw.get("values", raw.get("items", []))
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
            raw = []
        self._data = {str(v) for v in raw if v is not None}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(sorted(self._data), f, ensure_ascii=False, indent=2)

    def contains(self, value: str) -> bool:
        return str(value) in self._data

    def add(self, value: str) -> bool:
        value = str(value)
        if value in self._data:
            return False
        self._data.add(value)
        self._save()
        return True

    @property
    def values(self) -> Set[str]:
        return set(self._data)


class JsonResultsStore:
    """
    本地 JSON 结果存储，自动维护 URL 去重集合
    """

    def __init__(self, path: str):
        self.path = path
        self.results: List[Dict[str, Any]] = []
        self.seen_urls: Set[str] = set()
        self._load()

    def _load(self) -> None:
        raw = _safe_load_json(self.path, [])
        if isinstance(raw, dict):
            raw = raw.get("results", [])
        if not isinstance(raw, list):
            raw = []
        self.results = raw
        self.seen_urls = set()
        for item in self.results:
            if isinstance(item, dict):
                url = item.get("srcUrl") or item.get("url")
                if url:
                    self.seen_urls.add(str(url))

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.results, f, ensure_ascii=False, indent=2)

    def contains_url(self, url: str) -> bool:
        return str(url) in self.seen_urls

    def add_result(self, result: Dict[str, Any]) -> bool:
        url = ""
        if isinstance(result, dict):
            url = str(result.get("srcUrl") or result.get("url") or "")
        if url and self.contains_url(url):
            return False

        self.results.append(result)
        if url:
            self.seen_urls.add(url)
        self._save()
        return True
