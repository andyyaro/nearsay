"""macOS notifications and speech.

Text is passed to AppleScript as ``argv`` items, never pasted into the script
source, so quotes or backslashes in a task cannot break out of the string.
"""

from __future__ import annotations

from typing import Callable, List, Sequence

Runner = Callable[..., object]


class Notifier:
    def __init__(self, runner: Runner, enabled: bool = True, speak: bool = False):
        self.runner = runner
        self.enabled = enabled
        self.speak_enabled = speak
        self.sent: List[Sequence[str]] = []

    def notify(self, title: str, message: str, subtitle: str = "") -> None:
        if not self.enabled:
            return
        argv = [
            "osascript",
            "-e", "on run argv",
            "-e", "display notification (item 2 of argv) with title (item 1 of argv) subtitle (item 3 of argv)",
            "-e", "end run",
            title[:120], message[:240], subtitle[:120],
        ]
        self._run(argv)

    def speak(self, message: str) -> None:
        if self.speak_enabled:
            self._run(["say", message[:200]])

    def _run(self, argv: Sequence[str]) -> None:
        self.sent.append(list(argv))
        try:
            self.runner(argv, timeout=10)
        except Exception:
            pass  # a missing notification must never fail a launch
