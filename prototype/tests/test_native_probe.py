"""Load the production probe DLL into this Python test process, never into TF2."""
import ctypes
import os
from pathlib import Path
import unittest


DLL = Path(__file__).resolve().parents[1] / "native/out/tf2_step_probe.dll"


class ProbeStatus(ctypes.Structure):
    _fields_ = [(n, ctypes.c_uint32) for n in (
        "size", "abi", "initialized", "armed", "halted", "fault", "probe_required", "pending_state"
    )] + [(n, ctypes.c_uint64) for n in (
        "epoch", "completed_frame", "pending_frame", "outer_calls", "hold_calls", "advance_permits",
        "pause_permits", "completed_permits", "first_speed_reads", "second_speed_reads", "original_frame_time_us"
    )] + [(n, ctypes.c_uint32) for n in ("pending_dt_us", "reserved")]
    _fields_ += [(n, ctypes.c_uint64) for n in ("time_before_ms", "time_after_ms")]


@unittest.skipUnless(os.name == "nt" and DLL.exists(), "build isolated native prototype first")
class NativeProbePassiveTests(unittest.TestCase):
    def test_production_dll_stays_passive_in_non_game_process(self):
        dll = ctypes.CDLL(str(DLL))
        dll.TF2StepProbe_Initialize.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        dll.TF2StepProbe_Initialize.restype = ctypes.c_uint32
        dll.TF2StepProbe_GetStatus.argtypes = [ctypes.POINTER(ProbeStatus), ctypes.c_uint32]
        dll.TF2StepProbe_GetStatus.restype = ctypes.c_uint32
        dll.TF2StepProbe_Arm.argtypes = [ctypes.c_uint64]
        dll.TF2StepProbe_Arm.restype = ctypes.c_uint32
        state = ProbeStatus()
        self.assertEqual(ctypes.sizeof(state), 144)
        self.assertEqual(dll.TF2StepProbe_GetStatus(ctypes.byref(state), ctypes.sizeof(state)), 0)
        self.assertEqual((state.size, state.abi), (144, 3))
        self.assertEqual((state.initialized, state.armed, state.outer_calls), (0, 0, 0))
        self.assertEqual(state.probe_required, 1)
        self.assertEqual(dll.TF2StepProbe_Initialize(2, 0x51554945), 2)  # Obsolete ABI; no patch.
        self.assertEqual(dll.TF2StepProbe_Initialize(3, 0x51554945), 4)  # Wrong host; no patch.
        self.assertEqual(dll.TF2StepProbe_Arm(42), 3)  # No initialization, no permit.
        self.assertEqual(dll.TF2StepProbe_GetStatus(ctypes.byref(state), ctypes.sizeof(state)), 0)
        self.assertEqual((state.initialized, state.armed, state.outer_calls), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
