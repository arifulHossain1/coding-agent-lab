"""A deterministic answer-card client for repair-loop testing."""


class ScriptedClient:
    """Return predefined reply strings in their supplied order."""

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self._index = 0

    def chat(self, messages: list[dict[str, str]]) -> str:
        """Return the next reply or raise when the script is exhausted."""
        if self._index >= len(self._replies):
            raise RuntimeError("ScriptedClient exhausted: no predefined replies remain")
        reply = self._replies[self._index]
        self._index += 1
        return reply
