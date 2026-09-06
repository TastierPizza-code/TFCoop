// Experimental Transport Fever 2 build 35924 boundary adapter.
// No sleeps, file/network I/O, allocation or waiting on the simulation thread.
// HOLD uses the engine's own paused branch; Lua/command-pump liveness and the
// effect of its varying maintenance counter must still be measured in game.
#include "step_probe.h"
#include <windows.h>
#include <intrin.h>
#include <atomic>
#include <cstring>

namespace {
using StepFn = void(*)(void*, uint64_t, int);
using SpeedFn = int(*)(void*);
using ClockFn = uint64_t(*)(void*);
constexpr uintptr_t STEP_RVA = 0x15aa00;
constexpr uintptr_t SPEED_RVA = 0x2877a0;
constexpr uintptr_t FIRST_READ_RETURN_RVA = 0x15aa35;
constexpr uintptr_t SECOND_READ_RETURN_RVA = 0x15aae9;
constexpr unsigned STEP_STEAL = 21, SPEED_STEAL = 17;
const unsigned char STEP_PREFIX[STEP_STEAL] = {
    0x40,0x53,0x41,0x56,0x48,0x83,0xec,0x68,0x48,0x8b,0xda,
    0x4c,0x8b,0xf1,0x48,0x81,0xfa,0xe8,0x03,0x00,0x00};
const unsigned char SPEED_PREFIX[12] = {
    0x48,0x83,0xec,0x28,0x48,0x8d,0x51,0x10,0x48,0x8b,0x49,0x08};

std::atomic<uint32_t> initialized{0}, armed{0}, halted{0}, fault{0};
std::atomic<uint32_t> slot{0}, pendingDt{0}, completedDt{0};
std::atomic<uint64_t> epochId{0}, completedFrame{0}, pendingFrame{0};
std::atomic<uint64_t> outerCalls{0}, holds{0}, advances{0}, pauses{0}, completions{0};
std::atomic<uint64_t> firstReads{0}, secondReads{0}, originalFrameTime{0};
std::atomic<uint64_t> timeBefore{0}, timeAfter{0};
std::atomic_flag controlGate = ATOMIC_FLAG_INIT;
struct ControlGuard {
    bool acquired;
    ControlGuard() : acquired(!controlGate.test_and_set(std::memory_order_acquire)) {}
    ~ControlGuard() { if (acquired) controlGate.clear(std::memory_order_release); }
};
StepFn originalStep = nullptr;
SpeedFn originalSpeed = nullptr;
ClockFn engineTimeGetter = nullptr;
ClockFn readClock = nullptr;
uintptr_t firstReadReturn = 0, secondReadReturn = 0;
void* trampolinePage = nullptr; // Pinned hooks own this page until process exit.
thread_local bool inStep = false;
thread_local int permittedSpeed = 0;
thread_local unsigned readOne = 0, readTwo = 0;

uint64_t ReadGameClock(void* gameSim) {
    // Verified in the original Step and its caller before the buffer swap.
    auto* gameState = *reinterpret_cast<unsigned char**>(static_cast<unsigned char*>(gameSim) + 8);
    void* gameTime = *reinterpret_cast<void**>(gameState + 0x38);
    return engineTimeGetter(gameTime);
}

void LatchFault(uint32_t why) {
    uint32_t noFault = 0;
    fault.compare_exchange_strong(noFault, why);
    halted.store(1, std::memory_order_release);
}

int ReadSpeed(void* gameTime, uintptr_t returnAddress) {
    if (inStep && returnAddress == firstReadReturn) {
        ++readOne;
        firstReads.fetch_add(1, std::memory_order_relaxed);
        return permittedSpeed;
    }
    if (inStep && returnAddress == secondReadReturn) {
        ++readTwo;
        secondReads.fetch_add(1, std::memory_order_relaxed);
        return permittedSpeed;
    }
    return originalSpeed(gameTime); // GUI and all other readers are unchanged.
}

__declspec(noinline) int SpeedDetour(void* gameTime) {
    return ReadSpeed(gameTime, reinterpret_cast<uintptr_t>(_ReturnAddress()));
}

void StepDetour(void* gameSim, uint64_t frameTime, int mode) {
    outerCalls.fetch_add(1, std::memory_order_relaxed);
    originalFrameTime.store(frameTime, std::memory_order_relaxed);
    if (!armed.load(std::memory_order_acquire)) {
        originalStep(gameSim, frameTime, mode);
        return;
    }
    // Any unexpected re-entry is a structural fault. Do not recursively run the
    // engine while its Step is active; preserve the already latched outer frame.
    if (inStep) { LatchFault(TF2_PROBE_UNEXPECTED_SPEED_READ); return; }

    bool admitted = false;
    uint64_t frame = 0;
    uint32_t dt = 0;
    if (!halted.load(std::memory_order_acquire)) {
        uint32_t ready = 2;
        if (slot.compare_exchange_strong(ready, 3, std::memory_order_acq_rel)) {
            // The final halt observation is the admission linearization point.
            // A Halt racing after it permits only this already admitted frame.
            if (!halted.load(std::memory_order_acquire)) {
                admitted = true;
                frame = pendingFrame.load(std::memory_order_relaxed);
                dt = pendingDt.load(std::memory_order_relaxed);
            } else {
                slot.store(0, std::memory_order_release);
            }
        }
    }

    permittedSpeed = admitted && dt != 0 ? 1 : 0;
    if (!readClock) { LatchFault(TF2_PROBE_CLOCK_MISMATCH); return; }
    const uint64_t beforeMs = readClock(gameSim);
    timeBefore.store(beforeMs, std::memory_order_relaxed);
    readOne = readTwo = 0;
    inStep = true;
    // Both engine calls of GetSpeed see the same latched value. Speed 0 keeps
    // paused maintenance/script callbacks; speed 1 runs exactly one inner body.
    // Supply a valid 200 ms frame argument even for HOLD / dt=0. The actual
    // engine's EmissionMap update rejects sub-200 ms advancing traversals.
    originalStep(gameSim, TF2_PROBE_STEP_US, mode);
    inStep = false;
    const uint64_t afterMs = readClock(gameSim);
    timeAfter.store(afterMs, std::memory_order_release);

    // This checks control-flow conformance, not command success or determinism.
    if (readOne != 1 || readTwo != unsigned(permittedSpeed)) {
        LatchFault(TF2_PROBE_UNEXPECTED_SPEED_READ);
        if (admitted) slot.store(0, std::memory_order_release);
        return; // Never advertise an unverified engine traversal as complete.
    }
    if (afterMs < beforeMs || afterMs - beforeMs != (admitted ? dt / 1000u : 0u)) {
        LatchFault(TF2_PROBE_CLOCK_MISMATCH);
        if (admitted) slot.store(0, std::memory_order_release);
        return;
    }
    if (!admitted) {
        holds.fetch_add(1, std::memory_order_relaxed);
        return;
    }
    if (dt) advances.fetch_add(1, std::memory_order_relaxed);
    else pauses.fetch_add(1, std::memory_order_relaxed);
    completedDt.store(dt, std::memory_order_relaxed);
    completedFrame.store(frame, std::memory_order_release);
    completions.fetch_add(1, std::memory_order_relaxed);
    slot.store(0, std::memory_order_release);
}

uint64_t HashBytes(const unsigned char* bytes, size_t length) {
    uint64_t h = 14695981039346656037ull;
    for (size_t i = 0; i < length; ++i) h = (h ^ bytes[i]) * 1099511628211ull;
    return h;
}

// SEH is limited to read-only compatibility checks; a live engine fault must
// never be swallowed and misreported as a successfully completed permit.
bool VerifyImage(HMODULE module) {
    __try {
        const auto* base = reinterpret_cast<const unsigned char*>(module);
        const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
        if (dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
        const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
        if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.Machine != IMAGE_FILE_MACHINE_AMD64 ||
            nt->FileHeader.TimeDateStamp != 0x675abcc6 || nt->OptionalHeader.SizeOfImage != 0x046ce000)
            return false;
        // Entire Step, getter, outer loop and the downstream EmissionMap
        // precondition, not merely similar prologues. The constant is .2f.
        return HashBytes(base + STEP_RVA, 0x289) == 0x6040af1d4506ab88ull &&
               HashBytes(base + SPEED_RVA, 0x19) == 0xebde02e6df3c6fadull &&
               HashBytes(base + 0x287810, 0x19) == 0x2d0d2e17d5e259baull &&
               HashBytes(base + 0x1184d0, 0x48c) == 0x26105fce4d45adf1ull &&
               HashBytes(base + 0x2f7850, 0x28a) == 0xa6f5fd8ad67e9aeaull &&
               *reinterpret_cast<const uint32_t*>(base + 0x2f304c8) == 0x3e4ccccdu;
    } __except (EXCEPTION_EXECUTE_HANDLER) { return false; }
}

void WriteJump(unsigned char* out, const void* target) {
    const unsigned char prefix[6] = {0xff,0x25,0,0,0,0};
    std::memcpy(out, prefix, 6);
    std::memcpy(out + 6, &target, 8);
}

bool InstallPair(unsigned char* step, unsigned char* speed) {
    if (std::memcmp(step, STEP_PREFIX, STEP_STEAL) ||
        std::memcmp(speed, SPEED_PREFIX, 12) || speed[12] != 0xe8) return false;
    auto* page = static_cast<unsigned char*>(VirtualAlloc(nullptr, 4096,
        MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE));
    if (!page) return false;
    auto* stepTramp = page;
    auto* speedTramp = page + 128;
    std::memcpy(stepTramp, step, STEP_STEAL);
    WriteJump(stepTramp + STEP_STEAL, step + STEP_STEAL);
    // Getter's stolen bytes contain a rel32 call. Relocate it as an absolute
    // indirect CALL + jump over the target literal, retaining its return ABI.
    std::memcpy(speedTramp, speed, 12);
    const unsigned char callPrefix[8] = {0xff,0x15,0x02,0,0,0,0xeb,0x08};
    std::memcpy(speedTramp + 12, callPrefix, 8);
    int32_t displacement = 0;
    std::memcpy(&displacement, speed + 13, 4);
    const void* callee = speed + 17 + displacement;
    std::memcpy(speedTramp + 20, &callee, 8);
    WriteJump(speedTramp + 28, speed + SPEED_STEAL);
    DWORD pageOld = 0;
    if (!VirtualProtect(page, 4096, PAGE_EXECUTE_READ, &pageOld)) {
        VirtualFree(page, 0, MEM_RELEASE); return false;
    }
    FlushInstructionCache(GetCurrentProcess(), page, 4096);

    DWORD stepOld = 0, speedOld = 0;
    if (!VirtualProtect(step, STEP_STEAL, PAGE_EXECUTE_READWRITE, &stepOld)) {
        VirtualFree(page, 0, MEM_RELEASE); return false;
    }
    if (!VirtualProtect(speed, SPEED_STEAL, PAGE_EXECUTE_READWRITE, &speedOld)) {
        DWORD ignored = 0;
        VirtualProtect(step, STEP_STEAL, stepOld, &ignored);
        VirtualFree(page, 0, MEM_RELEASE); return false;
    }
    unsigned char stepSaved[STEP_STEAL], speedSaved[SPEED_STEAL];
    std::memcpy(stepSaved, step, STEP_STEAL);
    std::memcpy(speedSaved, speed, SPEED_STEAL);
    unsigned char stepPatch[STEP_STEAL], speedPatch[SPEED_STEAL];
    std::memset(stepPatch, 0x90, sizeof stepPatch);
    std::memset(speedPatch, 0x90, sizeof speedPatch);
    WriteJump(stepPatch, reinterpret_cast<const void*>(&StepDetour));
    WriteJump(speedPatch, reinterpret_cast<const void*>(&SpeedDetour));
    originalStep = reinterpret_cast<StepFn>(stepTramp);
    originalSpeed = reinterpret_cast<SpeedFn>(speedTramp);
    std::memcpy(speed, speedPatch, SPEED_STEAL);
    std::memcpy(step, stepPatch, STEP_STEAL);
    FlushInstructionCache(GetCurrentProcess(), speed, SPEED_STEAL);
    FlushInstructionCache(GetCurrentProcess(), step, STEP_STEAL);
    DWORD ignored = 0;
    const bool restoredStep = !!VirtualProtect(step, STEP_STEAL, stepOld, &ignored);
    const bool restoredSpeed = !!VirtualProtect(speed, SPEED_STEAL, speedOld, &ignored);
    if (!restoredStep || !restoredSpeed) {
        // Startup is quiescent by contract; restore both bodies on any failure.
        DWORD scratch = 0;
        if (VirtualProtect(step, STEP_STEAL, PAGE_EXECUTE_READWRITE, &scratch)) {
            std::memcpy(step, stepSaved, STEP_STEAL);
            VirtualProtect(step, STEP_STEAL, stepOld, &scratch);
        }
        if (VirtualProtect(speed, SPEED_STEAL, PAGE_EXECUTE_READWRITE, &scratch)) {
            std::memcpy(speed, speedSaved, SPEED_STEAL);
            VirtualProtect(speed, SPEED_STEAL, speedOld, &scratch);
        }
        FlushInstructionCache(GetCurrentProcess(), step, STEP_STEAL);
        FlushInstructionCache(GetCurrentProcess(), speed, SPEED_STEAL);
        // Keep trampolines alive even if rollback protections also failed.
        trampolinePage = page;
        return false;
    }
    trampolinePage = page;
    return true;
}
} // namespace

TF2_PROBE_API uint32_t TF2StepProbe_Initialize(uint32_t abi, uint32_t startup_quiescent) {
    if (abi != TF2_PROBE_ABI) return TF2_PROBE_BAD_ARGUMENT;
    if (startup_quiescent != TF2_PROBE_STARTUP_QUIESCENT) return TF2_PROBE_STARTUP_NOT_QUIESCENT;
    ControlGuard control;
    if (!control.acquired) return TF2_PROBE_BUSY;
    if (initialized.load()) return TF2_PROBE_DUPLICATE;
    if (halted.load()) return TF2_PROBE_HALTED;
    const HMODULE host = GetModuleHandleW(nullptr);
    wchar_t path[MAX_PATH] = {};
    if (!host || !GetModuleFileNameW(host, path, MAX_PATH)) return TF2_PROBE_WRONG_BUILD;
    const wchar_t* leaf = wcsrchr(path, L'\\');
    if (_wcsicmp(leaf ? leaf + 1 : path, L"TransportFever2.exe") || !VerifyImage(host))
        return TF2_PROBE_WRONG_BUILD;
    // A module containing patched destinations must never be unloaded.
    HMODULE pinned = nullptr;
    if (!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_PIN,
            reinterpret_cast<LPCWSTR>(&TF2StepProbe_Initialize), &pinned)) return TF2_PROBE_PATCH_FAILED;
    const uintptr_t base = reinterpret_cast<uintptr_t>(host);
    firstReadReturn = base + FIRST_READ_RETURN_RVA;
    secondReadReturn = base + SECOND_READ_RETURN_RVA;
    engineTimeGetter = reinterpret_cast<ClockFn>(base + 0x287810);
    readClock = ReadGameClock;
    if (!InstallPair(reinterpret_cast<unsigned char*>(base + STEP_RVA),
                     reinterpret_cast<unsigned char*>(base + SPEED_RVA))) {
        LatchFault(TF2_PROBE_PATCH_FAILED); return TF2_PROBE_PATCH_FAILED;
    }
    initialized.store(1, std::memory_order_release);
    return TF2_PROBE_OK;
}

TF2_PROBE_API uint32_t TF2StepProbe_Arm(uint64_t epoch) {
    if (!epoch) return TF2_PROBE_BAD_ARGUMENT;
    ControlGuard control;
    if (!control.acquired) return TF2_PROBE_BUSY;
    if (!initialized.load(std::memory_order_acquire)) return TF2_PROBE_NOT_INITIALIZED;
    if (armed.load()) return TF2_PROBE_ALREADY_ARMED;
    if (halted.load()) return TF2_PROBE_HALTED;
    if (outerCalls.load()) return TF2_PROBE_WORLD_ALREADY_STEPPED;
    epochId.store(epoch, std::memory_order_relaxed);
    armed.store(1, std::memory_order_release);
    return TF2_PROBE_OK;
}

TF2_PROBE_API uint32_t TF2StepProbe_Permit(uint64_t epoch, uint64_t frame, uint32_t dt_us) {
    if (!frame || (dt_us != 0 && dt_us != TF2_PROBE_STEP_US)) return TF2_PROBE_BAD_ARGUMENT;
    if (!armed.load(std::memory_order_acquire)) return TF2_PROBE_NOT_INITIALIZED;
    if (epoch != epochId.load()) return TF2_PROBE_WRONG_EPOCH;
    if (halted.load(std::memory_order_acquire)) return TF2_PROBE_HALTED;
    uint32_t empty = 0;
    if (!slot.compare_exchange_strong(empty, 1, std::memory_order_acq_rel)) {
        if (empty == 2 && pendingFrame.load() == frame && pendingDt.load() == dt_us)
            return TF2_PROBE_DUPLICATE;
        return TF2_PROBE_BUSY;
    }
    const uint64_t previous = completedFrame.load(std::memory_order_acquire);
    if (frame != previous + 1 || halted.load(std::memory_order_acquire)) {
        slot.store(0, std::memory_order_release);
        if (halted.load()) return TF2_PROBE_HALTED;
        return frame == previous && completedDt.load() == dt_us ? TF2_PROBE_DUPLICATE : TF2_PROBE_FRAME_ORDER;
    }
    pendingFrame.store(frame, std::memory_order_relaxed);
    pendingDt.store(dt_us, std::memory_order_relaxed);
    slot.store(2, std::memory_order_release);
    return TF2_PROBE_OK;
}

TF2_PROBE_API uint32_t TF2StepProbe_Halt(uint64_t epoch) {
    if (!armed.load(std::memory_order_acquire)) return TF2_PROBE_NOT_INITIALIZED;
    if (epoch != epochId.load()) return TF2_PROBE_WRONG_EPOCH;
    halted.store(1, std::memory_order_release);
    return TF2_PROBE_OK;
}

TF2_PROBE_API uint32_t TF2StepProbe_GetStatus(TF2ProbeStatus* status, uint32_t size) {
    if (!status || size != sizeof(TF2ProbeStatus)) return TF2_PROBE_BAD_ARGUMENT;
    TF2ProbeStatus s = {};
    s.size = sizeof s; s.abi = TF2_PROBE_ABI; s.probe_required = 1;
    s.initialized = initialized.load(); s.armed = armed.load(); s.halted = halted.load();
    s.fault = fault.load(); s.pending_state = slot.load(); s.epoch = epochId.load();
    s.completed_frame = completedFrame.load(); s.pending_frame = pendingFrame.load();
    s.outer_calls = outerCalls.load(); s.hold_calls = holds.load();
    s.advance_permits = advances.load(); s.pause_permits = pauses.load();
    s.completed_permits = completions.load(); s.first_speed_reads = firstReads.load();
    s.second_speed_reads = secondReads.load(); s.original_frame_time_us = originalFrameTime.load();
    s.pending_dt_us = pendingDt.load();
    s.time_before_ms = timeBefore.load(); s.time_after_ms = timeAfter.load(); *status = s;
    return TF2_PROBE_OK;
}

#ifdef TF2_STEP_PROBE_TEST
void TF2StepProbe_TestReset(TF2ProbeStepFn step, TF2ProbeSpeedFn speed, TF2ProbeClockFn clock) {
    initialized=1; armed=0; halted=0; fault=0; slot=0; pendingDt=0; completedDt=0;
    epochId=0; completedFrame=0; pendingFrame=0; outerCalls=0; holds=0;
    advances=0; pauses=0; completions=0; firstReads=0; secondReads=0; originalFrameTime=0;
    timeBefore=0; timeAfter=0; readClock=clock;
    originalStep=step; originalSpeed=speed; firstReadReturn=1; secondReadReturn=2;
    inStep=false; permittedSpeed=0; readOne=readTwo=0;
}
void TF2StepProbe_TestStep(void* game, uint64_t frame_time, int mode) { StepDetour(game, frame_time, mode); }
int TF2StepProbe_TestSpeed(void* game, unsigned which) { return ReadSpeed(game, which); }
bool TF2StepProbe_TestInstallStandins(void* step, void* speed) {
    return InstallPair(static_cast<unsigned char*>(step), static_cast<unsigned char*>(speed));
}
void TF2StepProbe_TestReadSites(void* first, void* second) {
    firstReadReturn=reinterpret_cast<uintptr_t>(first);
    secondReadReturn=reinterpret_cast<uintptr_t>(second);
}
#endif
