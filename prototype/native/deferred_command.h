#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <mutex>

namespace tf2coop::prototype {

// This adapter does not install a hook. All production gates default to false.
// It owns the *native* objects after capture, never their serialized pointers.
struct DeferredAbi {
    void* context = nullptr;
    std::uint64_t (*current_thread)(void*) noexcept = nullptr;
    void (*move_command)(void*, void*, void*) noexcept = nullptr;
    void (*move_function)(void*, void*, void*) noexcept = nullptr;
    void (*move_weak)(void*, void*, void*) noexcept = nullptr;
    void (*destroy_command)(void*, void*) noexcept = nullptr;
    void (*destroy_function)(void*, void*) noexcept = nullptr;
    void (*destroy_weak)(void*, void*) noexcept = nullptr;
    // Add consumes/destructs command, function and weak exactly as the game does.
    // It only submits work: its return is NOT successful application.
    void* (*add)(void*, std::uint64_t, void*, void*, void*, void*, void*) noexcept = nullptr;
    void (*destroy_result)(void*, void*) noexcept = nullptr;
    bool valid() const noexcept;
};

struct DeferredGates {
    bool build_fingerprint_verified = false;
    bool producer_thread_pump_verified = false;
    bool completion_observer_verified = false;
    bool maintenance_while_paused_verified = false;
};

struct NativeCapture {
    std::uint64_t id = 0;
    std::uint64_t epoch = 0;
    void* command_list = nullptr;
    void* command = nullptr;       // live 0x38-byte by-value argument
    void* callback = nullptr;      // live 0x40-byte MSVC std::function
    void* weak = nullptr;          // live 0x10-byte fifth Add argument
    void* result = nullptr;        // live 8-byte Add return-storage slot
    // These are assertions by the future caller adapter, not inferred from IDs.
    bool caller_discards_result = false;
    bool full_intent_serialized = false;
    bool intent_durably_accepted = false;
    bool source_layout_validated = false;
};

enum class DeferredStatus {
    accepted, granted, submitted, applied, drained, pending,
    halted, gates_closed, wrong_thread, bad_capture, duplicate_id, full,
    unknown_id, invalid_order, wrong_boundary, duplicate_completion,
    application_failed, wrong_result_storage, world_still_live
};

struct DeferredResult {
    std::uint64_t id = 0;
    std::uint64_t order = 0;
    std::uint64_t boundary = 0;
    bool success = false;
    std::int64_t result_entity = -1;
};

class DeferredCommandQueue {
public:
    static constexpr std::size_t capacity = 32;
    DeferredCommandQueue(DeferredAbi abi, DeferredGates gates,
                         std::uint64_t epoch, std::uint64_t producer_thread) noexcept;
    ~DeferredCommandQueue();
    DeferredCommandQueue(const DeferredCommandQueue&) = delete;
    DeferredCommandQueue& operator=(const DeferredCommandQueue&) = delete;

    // On every rejection, ALL source objects and result storage remain untouched.
    // A hook in an active session must halt on rejection; it must not fall through
    // to local Add. Only accepted authorizes suppressing the original call.
    DeferredStatus capture(const NativeCapture& call) noexcept;
    // Called only after the protocol commits a globally ordered boundary.
    // May be called by the network thread. No native function executes here.
    DeferredStatus grant(std::uint64_t id, std::uint64_t order,
                         std::uint64_t boundary) noexcept;
    // Must run on the verified Add producer thread, while the simulation gate is
    // closed at exactly boundary. Pausing must not prevent this maintenance pump.
    DeferredStatus drain(std::uint64_t boundary) noexcept;
    // Future completion observer reports the REAL apply callback, not Add return.
    DeferredStatus report_applied(std::uint64_t id, std::uint64_t boundary,
                                  bool success, std::int64_t result_entity) noexcept;
    bool take_result(DeferredResult& out) noexcept;
    void halt() noexcept;
    bool halted() const noexcept;
    std::size_t pending_count() const noexcept;
    // No synthetic callback is fired on shutdown. Only use after world detachment;
    // while a world is live, retained UI callbacks still have an outstanding duty.
    DeferredStatus shutdown(bool world_detached) noexcept;

private:
    enum class State { empty, captured, granted, submitting, submitted, completed };
    struct Slot {
        alignas(16) std::array<std::byte, 0x38> command{};
        alignas(16) std::array<std::byte, 0x40> callback{};
        alignas(16) std::array<std::byte, 0x10> weak{};
        State state = State::empty;
        bool owns_arguments = false;
        bool in_add = false;
        void* command_list = nullptr;
        DeferredResult result{};
    };
    DeferredStatus fail(DeferredStatus status) noexcept;
    void destroy_owned(Slot& slot) noexcept;
    Slot* find(std::uint64_t id) noexcept;
    bool on_producer() const noexcept;
    bool gates_open() const noexcept;
    DeferredAbi abi_;
    DeferredGates gates_;
    std::uint64_t epoch_;
    std::uint64_t producer_thread_;
    std::uint64_t highest_id_ = 0;
    std::uint64_t next_order_ = 1;
    std::uint64_t last_boundary_ = 0;
    bool halted_ = false;
    mutable std::mutex mutex_;
    std::array<Slot, capacity> slots_{};
};

// Optional Windows ABI binding. This only creates a function table, not hooks.
// Caller must independently hash the loaded module / on-disk matching image to
// SHA256 782b904a8f7bbdac1f7a18528f1a5c778691e5aa3087c37c351bf6912585175c.
// Exact local instruction anchors are checked too. A false proof returns {}.
DeferredAbi bind_build_35924_abi(void* module_base, bool exact_fingerprint_verified) noexcept;

} // namespace tf2coop::prototype
