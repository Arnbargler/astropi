"""Lease for one camera operator. Local-LAN coordination, not authentication."""
import secrets
import threading
import time


class ControlLease:
    def __init__(self, ttl=15.0, clock=time.monotonic):
        self.ttl = ttl
        self.clock = clock
        self._lock = threading.Lock()
        self._token = None
        self._deadline = 0.0

    def _live(self):
        return self._token is not None and self.clock() < self._deadline

    def held(self):
        with self._lock:
            return self._live()

    def take(self):
        with self._lock:
            if self._live():
                return None
            self._token = secrets.token_urlsafe(24)
            self._deadline = self.clock() + self.ttl
            return self._token

    def owns(self, token):
        with self._lock:
            return bool(token) and self._live() and secrets.compare_digest(token, self._token)

    def renew(self, token):
        with self._lock:
            if not token or not self._live() or not secrets.compare_digest(token, self._token):
                return False
            self._deadline = self.clock() + self.ttl
            return True

    def release(self, token):
        with self._lock:
            if not token or not self._live() or not secrets.compare_digest(token, self._token):
                return False
            self._token = None
            self._deadline = 0
            return True
