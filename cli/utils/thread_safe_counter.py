import threading


class ThreadSafeCounter:
    def __init__(self, initial=0):
        self.value = initial
        self._lock = threading.Lock()

    def increment(self):
        with self._lock:
            self.value += 1
            return self.value

    def get_value(self):
        with self._lock:
            return self.value
