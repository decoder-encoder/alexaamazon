"""
Focus-music channels. Neither backend needs a music-service API key.

LocalPlayerMusic (default)
    Launches the mpv command-line player on the machine that runs this server
    and points it at a folder of audio files you own or that are openly
    licensed (Creative Commons, public domain). Audio is shuffled and loops
    until the session ends, then the player process is terminated.

WebhookMusic
    POSTs play/stop JSON to a URL, typically a small local web page that plays
    tracks with the HTML5 audio element, for example when you want the music in
    a browser tab.
"""

from __future__ import annotations

import asyncio
import shutil
from asyncio.subprocess import DEVNULL, Process
from pathlib import Path

from ..core.http import WebhookClient
from ..core.results import ChannelResult
from .base import Channel

AUDIO_EXTENSIONS = frozenset({".mp3", ".ogg", ".flac", ".wav", ".m4a", ".opus"})
MAX_TRACKS = 500  # Keeps the player's command line within OS limits.
STARTUP_CHECK_SECONDS = 0.5  # Lets a player that fails at launch be reported right away.
STOP_TIMEOUT_SECONDS = 5.0


class LocalPlayerMusic(Channel):
    """Plays a local music folder through mpv, with no network service involved."""

    name = "music"

    def __init__(self, music_dir: str | None, player: str) -> None:
        self._dir = Path(music_dir).expanduser() if music_dir else None
        self._player = player
        self._process: Process | None = None
        self._lock = asyncio.Lock()

    def missing_config(self) -> str | None:
        if self._dir is None:
            return "MUSIC_DIR is not set; point it at a folder of audio files"
        if not self._dir.is_dir():
            return f"MUSIC_DIR is not a directory: {self._dir}"
        if shutil.which(self._player) is None:
            return f"'{self._player}' was not found on PATH; install mpv to use local music"
        return None

    def _is_running(self) -> bool:
        return self._process is not None and self._process.returncode is None

    def _list_tracks(self) -> list[Path]:
        assert self._dir is not None  # Guaranteed by missing_config().
        return sorted(
            path
            for path in self._dir.iterdir()
            if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
        )

    async def _start(self, duration_minutes: int) -> ChannelResult:
        async with self._lock:
            if self._is_running():
                return ChannelResult.success(self.name, "music is already playing")

            # Directory listing is blocking I/O, so it runs in a worker thread.
            tracks = await asyncio.to_thread(self._list_tracks)
            if not tracks:
                return ChannelResult.failure(
                    self.name, "no_tracks", f"no supported audio files found in {self._dir}"
                )

            self._process = await asyncio.create_subprocess_exec(
                self._player,
                "--no-video",
                "--no-terminal",
                "--really-quiet",
                "--shuffle",
                "--loop-playlist=inf",
                *(str(track) for track in tracks[:MAX_TRACKS]),
                stdin=DEVNULL,
                stdout=DEVNULL,
                stderr=DEVNULL,
            )

            await asyncio.sleep(STARTUP_CHECK_SECONDS)
            if self._process.returncode is not None:
                exit_code = self._process.returncode
                self._process = None
                return ChannelResult.failure(
                    self.name,
                    "player_exited",
                    f"{self._player} exited immediately with code {exit_code}",
                )

            return ChannelResult.success(self.name, f"playing {min(len(tracks), MAX_TRACKS)} tracks")

    async def _stop(self) -> ChannelResult:
        async with self._lock:
            process = self._process
            self._process = None
            if process is None or process.returncode is not None:
                return ChannelResult.success(self.name, "nothing was playing")

            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=STOP_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            return ChannelResult.success(self.name, "music stopped")


class WebhookMusic(Channel):
    """Notifies a browser dashboard that plays audio with the HTML5 audio element."""

    name = "music"

    def __init__(self, url: str | None, http: WebhookClient) -> None:
        self._url = url
        self._http = http

    def missing_config(self) -> str | None:
        return None if self._url else "MUSIC_WEBHOOK_URL is not set"

    async def _start(self, duration_minutes: int) -> ChannelResult:
        return await self._http.request(
            self.name,
            "POST",
            self._url or "",
            json_body={"action": "play", "duration_minutes": duration_minutes},
        )

    async def _stop(self) -> ChannelResult:
        return await self._http.request(
            self.name,
            "POST",
            self._url or "",
            json_body={"action": "stop"},
        )
