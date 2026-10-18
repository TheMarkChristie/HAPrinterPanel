"""Moonraker on the printer (the K2 runs it beside Creality's own service, on port 7125, as Fluidd and Mainsail use it):
where the printer is in the file it is printing, the file itself, and the reboot. Plain HTTP, no Home Assistant in it
beyond the session it is given."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import aiohttp

from .gcode import LineIndex

PORT = 7125
QUERY = ("/printer/objects/query?virtual_sdcard=file_position,file_size"
         "&print_stats=state,filename,print_duration")
TIMEOUT = aiohttp.ClientTimeout(total=10)
FILE_TIMEOUT = aiohttp.ClientTimeout(total=600, sock_read=30)
CHUNK = 1 << 16


class MoonrakerError(Exception):
    """Moonraker could not be reached (unreachable), said no (refused), or dropped the connection (gone: a reboot does)."""

    def __init__(self, key: str, detail: str = "") -> None:
        super().__init__(detail or key)
        self.key = key
        self.detail = detail


@dataclass(frozen=True)
class Place:
    """Where the printer is: Moonraker's print state (standby, printing, paused, complete, cancelled, error), the file
    (from the gcodes folder), the position in it, its size, and the time spent printing it (pauses left out)."""

    state: str
    file: str
    position: int
    size: int
    printing_for: float


class Moonraker:
    """One printer's Moonraker."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int = PORT) -> None:
        host = host.strip()
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"  # an IPv6 address
        self._base = f"http://{host}:{port}"
        self._session = session

    async def place(self) -> Place:
        status = ((await self._json("GET", QUERY)).get("result") or {}).get("status") or {}
        sd, stats = status.get("virtual_sdcard") or {}, status.get("print_stats") or {}
        return Place(state=str(stats.get("state") or ""), file=str(stats.get("filename") or ""),
                     position=int(sd.get("file_position") or 0), size=int(sd.get("file_size") or 0),
                     printing_for=float(stats.get("print_duration") or 0))

    async def index(self, file: str) -> LineIndex:
        """Read the G-code file from the printer, keeping only where its lines end."""
        index = LineIndex()
        try:
            async with self._session.get(f"{self._base}/server/files/gcodes/{quote(file)}", timeout=FILE_TIMEOUT) as resp:
                if resp.status != 200:
                    raise MoonrakerError("refused", f"HTTP {resp.status}")
                async for chunk in resp.content.iter_chunked(CHUNK):
                    index.feed(chunk)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise MoonrakerError("unreachable", str(err) or type(err).__name__) from err
        return index.finish()

    async def reboot(self) -> None:
        """Restart the whole printer. Moonraker answers before it goes, or the connection drops as it goes: both are a
        restart under way."""
        try:
            await self._json("POST", "/machine/reboot")
        except MoonrakerError as err:
            if err.key != "gone":
                raise

    async def _json(self, method: str, path: str) -> dict[str, Any]:
        try:
            async with self._session.request(method, self._base + path, timeout=TIMEOUT) as resp:
                if resp.status != 200:
                    raise MoonrakerError("refused", await _said(resp))
                return await resp.json(content_type=None)
        except aiohttp.ServerDisconnectedError as err:
            raise MoonrakerError("gone", str(err) or "disconnected") from err
        except (aiohttp.ClientError, TimeoutError, ValueError) as err:
            raise MoonrakerError("unreachable", str(err) or type(err).__name__) from err


async def _said(resp: aiohttp.ClientResponse) -> str:
    """What Moonraker said with a refusal: its error message ({"error": {"message": ...}}), else the HTTP status."""
    try:
        body = await resp.json(content_type=None)
        message = ((body or {}).get("error") or {}).get("message")
    except (aiohttp.ClientError, ValueError):
        message = None
    return f"HTTP {resp.status}: {message}" if message else f"HTTP {resp.status}"
