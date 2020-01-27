import functools
import logging
import queue
import threading
import warnings

class ThreadWorker(threading.Thread):
    STOP = object()
    class NotStarted(Exception):
        pass
    class Timeout(Exception):
        pass

    def __init__(self, *, name=None, daemon=None):
        super().__init__(name=name, daemon=daemon)
        self._q = queue.Queue()

    def run(self):
        while True:
            f, evt, args, kwargs = self._q.get()
            if f is self.STOP:
                return
            if evt:
                try:
                    evt.res = f(*args, **kwargs)
                except Exception as ex:
                    evt.exc = ex
                evt.set()
            else:
                try:
                    f(*args, **kwargs)
                except Exception as ex:
                    warnings.warn(UserWarning("Uncought Exception in Threadworker Job", ex))

    def post_async(self, f, args=(), kwargs={}):
        self._q.put((f, None, args, kwargs))

    def post_sync(self, f, args, kwargs, timeout=None):
        if threading.current_thread() == self:
            return f(*args, **kwargs)

        if not self.is_alive():
            raise self.NotStarted()
        evt = threading.Event()
        self._q.put((f, evt, args, kwargs))
        if not evt.wait(timeout):
            raise Timeout()
        try:
            return evt.res
        except AttributeError:
            raise evt.exc from None

    def stop(self, timeout=None):
        self.post_async(self.STOP)
        self.join(timeout)

    def __del__(self):
        if self.is_alive():
            try:
                self.stop()
            except:
                pass
            if not self.daemon:
                warnings.warn(ResourceWarning("ThreadWorker was not stopped", self), source=self)

    def async(self, f):
        @functools.wraps(f)
        def proxy(*args, **kwargs):
            self.post_async(f, args, kwargs)
        return proxy

    def sync(self, f):
        @functools.wraps(f)
        def proxy(*args, **kwargs):
            return self.post_sync(f, args, kwargs)
        return proxy

class ThreadWorkerMixin:
    THREAD_WORKER_DAEMON = None
    THREAD_WORKER_NAME = None
    _thread_worker = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._thread_worker is None:
            self._thread_worker = ThreadWorker(daemon=self.THREAD_WORKER_DAEMON, name=self.THREAD_WORKER_NAME)
        self._thread_worker.start()

    def stop_thredworker(self):
        self._thread_worker.stop()

    @staticmethod
    def async(f):
        @functools.wraps(f)
        def proxy(*args, **kwargs):
            args[0]._thread_worker.post_async(f, args, kwargs)
        return proxy

    @staticmethod
    def sync(timeout_or_function):
        def deco(f):
            @functools.wraps(f)
            def proxy(*args, **kwargs):
                return args[0]._thread_worker.post_sync(f, args, kwargs, timeout=timeout)
            return proxy
        if callable(timeout_or_function):
            timeout = None
            return deco(timeout_or_function)
        else:
            timeout = timeout_or_function
            return deco

