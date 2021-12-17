try:
    from .threadworker import ThreadWorker, ThreadWorkerMixin
except ImportError:
    from .threadworker import ThreadWorker, ThreadWorkerMixin

import time
import unittest


class TWTest(unittest.TestCase):
    def setUp(self):
        self.tw = ThreadWorker(name=self._testMethodName)
        self.tw.start()

    def tearDown(self):
        self.tw.stop()

    def test_async(self):
        l = []

        @self.tw.async_call
        def f(i):
            time.sleep(0.1)
            l.append(i)

        f(42)
        assert l == []
        time.sleep(0.2)
        assert l == [42]

    def test_sync(self):
        l = []

        @self.tw.sync_call
        def f(i):
            time.sleep(0.1)
            l.append(i)
            return 42

        r = f(36)

        assert r == 42
        assert l == [36]

    def test_sync_ex(self):
        class SomeExc(Exception):
            pass

        @self.tw.sync_call
        def f():
            raise SomeExc()

        with self.assertRaises(SomeExc):
            f()

    def test_sync_from_async(self):
        """sync function should be executed inline."""
        l = []

        @self.tw.sync_call
        def f():
            l.append(2)
            return 3

        @self.tw.sync_call
        def g():
            l.append(1)
            l.append(f())

        g()
        time.sleep(0.1)
        assert l == [1, 2, 3]

    def test_async_from_sync(self):
        l = []

        @self.tw.async_call
        def f(x):
            l.append(x)

        @self.tw.sync_call
        def g(x):
            f(x)
            time.sleep(0.1)  # block tw, f not invoked yet
            return list(l)

        r = g(42)
        time.sleep(0.1)  # tw free to work on f now

        assert l == [42]
        assert r == []

    def test_stop_joins(self):
        l = []

        @self.tw.async_call
        def f():
            time.sleep(0.1)
            l.append(1)

        f()
        assert l == []
        self.tw.stop()
        assert l == [1]

    def test_async_not_started_works(self):
        l = []
        tw = ThreadWorker(name=self._testMethodName)

        @tw.async_call
        def f():
            time.sleep(0.1)
            l.append(1)

        f()
        assert l == []
        tw.start()
        assert l == []
        tw.stop()
        assert l == [1]

    def test_sync_not_started_raises(self):
        tw = ThreadWorker(name=self._testMethodName)

        @tw.sync_call
        def f():
            pass

        with self.assertRaises(tw.NotStarted):
            f()

    def test_resourceWarn(self):
        l = []
        tw = ThreadWorker(name=self._testMethodName)
        tw.start()

        @tw.async_call
        def f():
            time.sleep(0.1)
            l.append(1)

        f()
        assert l == []
        with self.assertWarns(ResourceWarning):
            # del tw # does not work
            tw.__del__()  # hacky but works
        assert l == [1]

    def test_no_resourceWarn_not_started(self):
        l = []
        tw = ThreadWorker(name=self._testMethodName, daemon=False)

        @tw.async_call
        def f():
            l.append(1)

        f()

        # del tw # does not work
        tw.__del__()  # hacky but works

        time.sleep(0.1)
        assert l == []

    def test_no_resourceWarn_daemon(self):
        l = []
        tw = ThreadWorker(name=self._testMethodName, daemon=True)
        tw.start()

        @tw.async_call
        def f():
            time.sleep(0.1)
            l.append(1)

        f()
        assert l == []
        # del tw # does not work
        tw.__del__()  # hacky but works

        assert l == [1]


class TWMITest(unittest.TestCase):
    class TWMI(ThreadWorkerMixin):
        THREAD_WORKER_DAEMON = True

        x = y = None

        @ThreadWorkerMixin.sync_call
        def s(self):
            self.x = 1
            time.sleep(0.1)
            self.y = 2

            return 3

        @ThreadWorkerMixin.async_call
        def a(self):
            self.x = 1
            time.sleep(0.2)
            self.y = 2

    def test_async(self):
        t = self.TWMI()
        assert t.x == t.y is None

        r = t.a()
        assert r is None

        time.sleep(0.1)
        assert t.x == 1
        assert t.y is None
        t.stop_thredworker()
        assert t.y == 2

    def test_sync(self):
        t = self.TWMI()
        assert t.x == t.y is None
        r = t.s()

        assert r == 3
        assert t.x == 1
        assert t.y == 2


if __name__ == "__main__":
    unittest.main(warnings="error")
