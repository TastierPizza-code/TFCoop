// Explicit opt-in, bounded file mailbox for the experimental Step probe.
// This never installs a mod, starts a game, or activates from DllMain.
#pragma once
#include "step_probe.h"

enum TF2ProbeRuntimeResult : uint32_t {
    TF2_RUNTIME_BAD_DIRECTORY = 100,
    TF2_RUNTIME_BAD_RECORD = 101,
    TF2_RUNTIME_IO_ERROR = 102,
    TF2_RUNTIME_REQUEST_ORDER = 103,
    TF2_RUNTIME_REQUEST_CONFLICT = 104,
    TF2_RUNTIME_THREAD_ERROR = 105,
    TF2_RUNTIME_STOP_TIMEOUT = 106,
    TF2_RUNTIME_INTERNAL_ERROR = 107,
};

// Calls Initialize+Arm synchronously, BEFORE the first engine Step. The caller
// must be outside DllMain and provide the explicit startup-quiescence contract.
// absolute_session_dir must already exist. One producer atomically replaces
// native_control.txt, retaining a request until its native acknowledgement.
// File-open/replacement sharing collisions retry for at most 250 ms on the
// worker; missing consumed records and other I/O failures remain terminal.
// Text diagnostics retain the FIRST fault's io_operation: 0 none, 1 control
// open, 2 control size, 3 control read, 4 status open, 5 status write,
// 6 status flush, 7 status replace. The C status ABI is unchanged.
TF2_PROBE_API uint32_t TF2StepProbe_RuntimeStart(
    const wchar_t* absolute_session_dir, uint64_t epoch, uint32_t startup_quiescent);

// Permanently halts the gate, then stops only this IPC worker. Never stops the
// game process. No runtime restart or re-arm is allowed before process exit.
TF2_PROBE_API uint32_t TF2StepProbe_RuntimeStop(uint64_t epoch);

#ifdef TF2_STEP_PROBE_TEST
// Only after RuntimeStop has joined its worker. No engine hooks are removed.
void TF2StepProbe_RuntimeTestReset();
// Synchronizes deliberate real-handle contention tests with the worker's first
// failed Windows call; tests do not assume disk flushes finish in a fixed time.
uint64_t TF2StepProbe_RuntimeTestContentions(bool control);
#endif
