"""Download the ai.engineer public corpus into data/raw."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx

COLLECTIONS = ["talks", "speakers", "topics", "organizations", "chapters", "transcripts"]
USER_AGENT = "aie-archive/0.1 (local transcript archive)"
RETRY_BASE_SECONDS = float(os.environ.get("AIE_RETRY_BASE", "10"))
MAX_ATTEMPTS = 4  # one try plus three retries
MAX_CONSECUTIVE_FAILURES = 3


class FetchError(Exception):
    """A file could not be fetched after all retries."""


@dataclass
class SyncResult:
    corpus_version: str | None = None
    up_to_date: bool = False
    fetched: int = 0
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    aborted: bool = False
    last_error: str | None = None

    @property
    def ok(self) -> bool:
        return not self.failed and not self.aborted


def write_atomic(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class Fetcher:
    """One request at a time, a pause after each, retries with exponential backoff."""

    def __init__(self, client: httpx.Client, delay: float, log):
        self.client = client
        self.delay = delay
        self.log = log

    def get_json_bytes(self, url: str) -> bytes:
        """Return the body of a 200 response that parses as JSON, or raise FetchError.

        Retries on 429, 529, any 5xx, transport errors, and bodies that are not
        valid JSON. Does not retry other statuses such as 404.
        """
        last_error = "unknown error"
        for attempt in range(MAX_ATTEMPTS):
            if attempt:
                wait = RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                self.log(f"  retry {attempt}/{MAX_ATTEMPTS - 1} in {wait:g}s ({last_error})")
                time.sleep(wait)
            try:
                response = self.client.get(url)
            except httpx.TransportError as e:
                last_error = f"{type(e).__name__}: {e}"
                time.sleep(self.delay)
                continue
            time.sleep(self.delay)
            if response.status_code == 200:
                try:
                    json.loads(response.content)
                except ValueError:
                    last_error = "body is not valid JSON"
                    continue
                return response.content
            if response.status_code in (429, 529) or response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
                continue
            raise FetchError(f"HTTP {response.status_code}")
        raise FetchError(last_error)


def sync(data_dir: Path, base_url: str, delay: float = 2.0, force: bool = False, log=print) -> SyncResult:
    raw = data_dir / "raw"
    (raw / "transcripts").mkdir(parents=True, exist_ok=True)
    result = SyncResult()
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60, follow_redirects=True) as client:
        fetcher = Fetcher(client, delay, log)
        try:
            status_bytes = fetcher.get_json_bytes(f"{base_url}/api/data/status")
        except FetchError as e:
            result.failed.append("status")
            result.last_error = str(e)
            result.aborted = True
            return result
        result.corpus_version = json.loads(status_bytes).get("corpusVersion")

        version_file = raw / "version.json"
        if not force and version_file.exists():
            local = json.loads(version_file.read_text()).get("corpusVersion")
            if local == result.corpus_version:
                result.up_to_date = True
                log(f"up to date (corpus {str(result.corpus_version)[:12]})")
                return result
        write_atomic(raw / "status.json", status_bytes)

        consecutive_failures = 0

        def download(name: str, url: str, dest: Path) -> bool:
            """Fetch one file. Return False when the circuit breaker has tripped."""
            nonlocal consecutive_failures
            try:
                write_atomic(dest, fetcher.get_json_bytes(url))
                result.fetched += 1
                consecutive_failures = 0
                return True
            except FetchError as e:
                result.failed.append(name)
                result.last_error = str(e)
                consecutive_failures += 1
                log(f"  failed: {name} ({e})")
                return consecutive_failures < MAX_CONSECUTIVE_FAILURES

        for name in COLLECTIONS:
            log(f"fetching {name}")
            if not download(name, f"{base_url}/api/data/{name}?format=json", raw / f"{name}.json"):
                result.aborted = True
                return result

        index_file = raw / "transcripts.json"
        if not index_file.exists():
            return result
        entries = json.loads(index_file.read_text())
        for i, entry in enumerate(entries, 1):
            slug = entry["talkSlug"]
            dest = raw / "transcripts" / f"{slug}.json"
            if dest.exists() and not force:
                result.skipped += 1
                continue
            log(f"[{i}/{len(entries)}] transcript {slug}")
            if not download(f"transcript:{slug}", f"{base_url}/api/data/transcript?slug={slug}&format=json", dest):
                result.aborted = True
                return result

        if result.ok:
            version = {"corpusVersion": result.corpus_version,
                       "syncedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            write_atomic(version_file, json.dumps(version).encode())
    return result
