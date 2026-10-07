from __future__ import annotations

import unittest

from ml.weight_baseline.rgb_multiview_v002 import (
    _bar,
    _duration,
    _resolve_device,
)


class FakeCuda:
    def __init__(self, available: bool):
        self._available = available

    def is_available(self):
        return self._available

    def device_count(self):
        return 1 if self._available else 0

    def get_device_name(self, index):
        return "Fake GPU"


class FakeTorch:
    __version__ = "test"

    class version:
        cuda = "test-cuda"

    def __init__(self, available: bool):
        self.cuda = FakeCuda(available)

    class _Device:
        def __init__(self, name: str):
            self.type = name.split(":", 1)[0]
            self.name = name

        def __str__(self):
            return self.name

    def device(self, name: str):
        return self._Device(name)


class WeightRgbV002LogUxGpuGuardTest(unittest.TestCase):
    def test_bar_is_readable(self):
        self.assertEqual(_bar(0, 10, 10), "[----------]")
        self.assertEqual(_bar(5, 10, 10), "[#####-----]")
        self.assertEqual(_bar(10, 10, 10), "[##########]")

    def test_duration_formats(self):
        self.assertEqual(_duration(5), "5s")
        self.assertEqual(_duration(65), "1m 05s")
        self.assertEqual(_duration(3660), "1h 01m")

    def test_cpu_is_blocked_by_default_when_cuda_unavailable(self):
        torch = FakeTorch(False)
        with self.assertRaisesRegex(RuntimeError, "CPU training is blocked"):
            _resolve_device(torch, device_name=None, allow_cpu=False)

    def test_cpu_can_be_explicitly_allowed(self):
        torch = FakeTorch(False)
        device, diagnostics = _resolve_device(
            torch,
            device_name=None,
            allow_cpu=True,
        )
        self.assertEqual(device.type, "cpu")
        self.assertFalse(diagnostics["cuda_available"])

    def test_cuda_is_selected_when_available(self):
        torch = FakeTorch(True)
        device, diagnostics = _resolve_device(
            torch,
            device_name=None,
            allow_cpu=False,
        )
        self.assertEqual(device.type, "cuda")
        self.assertTrue(diagnostics["cuda_available"])
        self.assertEqual(diagnostics["cuda_device_names"], ["Fake GPU"])


if __name__ == "__main__":
    unittest.main()
