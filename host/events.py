# host/events.py
from dataclasses import dataclass
import socket as _socket


@dataclass
class KeystrokeEvent:
    timestamp: float


@dataclass
class MouseMoveEvent:
    timestamp: float


@dataclass
class GitPushEvent:
    branch: str


@dataclass
class UploadRequestEvent:
    conn: _socket.socket


@dataclass
class WeatherUpdateEvent:
    text: str


@dataclass
class TempRequestEvent:
    pass


@dataclass
class TickEvent:
    pass
