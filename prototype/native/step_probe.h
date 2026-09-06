// EXPERIMENTAL engine boundary probe, never loaded or installed automatically.
// A permit limits engine advancement; it does NOT prove world determinism.
// Initialize and Arm must run before the first GameSim::Step, with game startup
// quiescent. Once hooks are installed the module must stay loaded until exit.
// Concurrent control calls return BUSY rather than patching/arming twice.
#pragma once
#include <stdint.h>

#ifdef _WIN32
# define TF2_PROBE_API extern "C" __declspec(dllexport)
#else
# define TF2_PROBE_API extern "C"
#endif

enum TF2ProbeResult : uint32_t {
    TF2_PROBE_OK = 0,
    TF2_PROBE_DUPLICATE = 1,
    TF2_PROBE_BAD_ARGUMENT = 2,
    TF2_PROBE_NOT_INITIALIZED = 3,
    TF2_PROBE_WRONG_BUILD = 4,
    TF2_PROBE_PATCH_FAILED = 5,
    TF2_PROBE_STARTUP_NOT_QUIESCENT = 6,
    TF2_PROBE_ALREADY_ARMED = 7,
    TF2_PROBE_HALTED = 8,
    TF2_PROBE_BUSY = 9,
    TF2_PROBE_WRONG_EPOCH = 10,
    TF2_PROBE_FRAME_ORDER = 11,
    TF2_PROBE_WORLD_ALREADY_STEPPED = 12,
    TF2_PROBE_UNEXPECTED_SPEED_READ = 13,
    TF2_PROBE_CLOCK_MISMATCH = 14,
};

// ABI 3 changes the engine-step contract from the invalid 100 ms experiment to
// 200 ms. The diagnostic C struct layout remains unchanged from ABI 2.
static const uint32_t TF2_PROBE_ABI = 3;
// Deliberate acknowledgement; this is NOT a test for thread quiescence.
static const uint32_t TF2_PROBE_STARTUP_QUIESCENT = 0x51554945;
// Build 35924 EmissionMap::Update requires dt >= .2f (seconds). GameSim converts
// microseconds to integer milliseconds, then to float seconds. Do not shorten
// this step or patch out the engine's assertion to conceal an invalid caller.
static const uint32_t TF2_PROBE_STEP_US = 200000;

struct TF2ProbeStatus {
    uint32_t size;
    uint32_t abi;
    uint32_t initialized;
    uint32_t armed;
    uint32_t halted;
    uint32_t fault;
    uint32_t probe_required;       // Always 1: paused maintenance changes counters.
    uint32_t pending_state;        // 0 empty, 1 publishing, 2 ready, 3 executing.
    uint64_t epoch;
    uint64_t completed_frame;
    uint64_t pending_frame;
    uint64_t outer_calls;          // GameSim::Step calls, NOT simulation steps.
    uint64_t hold_calls;
    uint64_t advance_permits;
    uint64_t pause_permits;
    uint64_t completed_permits;
    uint64_t first_speed_reads;
    uint64_t second_speed_reads;
    uint64_t original_frame_time_us;
    uint32_t pending_dt_us;
    uint32_t reserved;
    uint64_t time_before_ms;       // Actual engine clock, observed on sim thread.
    uint64_t time_after_ms;
};

// Only Transport Fever 2 build 35924, exact verified code bodies. Refuses the
// currently installed Alpha's existing Step detour instead of stacking hooks.
TF2_PROBE_API uint32_t TF2StepProbe_Initialize(uint32_t abi, uint32_t startup_quiescent);
TF2_PROBE_API uint32_t TF2StepProbe_Arm(uint64_t epoch);
// Frames start at 1 and must be contiguous. dt_us is 0 (paused maintenance) or
// exactly 200000. A caller retries BUSY; duplicate permits never run twice.
TF2_PROBE_API uint32_t TF2StepProbe_Permit(uint64_t epoch, uint64_t frame, uint32_t dt_us);
// Permanent until process exit. An already admitted step may finish; no next
// step can be admitted. This does not terminate or block the game thread.
TF2_PROBE_API uint32_t TF2StepProbe_Halt(uint64_t epoch);
// A bounded, individually atomic diagnostic snapshot, not a world-state hash.
TF2_PROBE_API uint32_t TF2StepProbe_GetStatus(TF2ProbeStatus* status, uint32_t size);

#ifdef TF2_STEP_PROBE_TEST
using TF2ProbeStepFn = void(*)(void*, uint64_t, int);
using TF2ProbeSpeedFn = int(*)(void*);
using TF2ProbeClockFn = uint64_t(*)(void*);
void TF2StepProbe_TestReset(TF2ProbeStepFn step, TF2ProbeSpeedFn speed, TF2ProbeClockFn clock = nullptr);
void TF2StepProbe_TestStep(void* game, uint64_t frame_time, int mode);
int TF2StepProbe_TestSpeed(void* game, unsigned which);
bool TF2StepProbe_TestInstallStandins(void* step, void* speed);
void TF2StepProbe_TestReadSites(void* first, void* second);
#endif
