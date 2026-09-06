#include "deferred_command.h"

#include <cstring>
#include <limits>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#endif

namespace tf2coop::prototype {

namespace {
bool disjoint_sources(const NativeCapture& c) noexcept {
    const void* pointers[] = {c.command, c.callback, c.weak, c.result};
    const std::uintptr_t sizes[] = {0x38, 0x40, 0x10, sizeof(void*)};
    for (std::size_t i = 0; i < 4; ++i) {
        const auto begin = reinterpret_cast<std::uintptr_t>(pointers[i]);
        if (begin % alignof(void*) != 0 || begin > std::numeric_limits<std::uintptr_t>::max() - sizes[i])
            return false;
        for (std::size_t j = 0; j < i; ++j) {
            const auto other = reinterpret_cast<std::uintptr_t>(pointers[j]);
            if (begin < other + sizes[j] && other < begin + sizes[i]) return false;
        }
    }
    return true;
}
} // namespace

bool DeferredAbi::valid() const noexcept {
    return current_thread && move_command && move_function && move_weak &&
        destroy_command && destroy_function && destroy_weak && add && destroy_result;
}

DeferredCommandQueue::DeferredCommandQueue(DeferredAbi abi, DeferredGates gates,
    std::uint64_t epoch, std::uint64_t producer_thread) noexcept
    : abi_(abi), gates_(gates), epoch_(epoch), producer_thread_(producer_thread) {}

DeferredCommandQueue::~DeferredCommandQueue() {
    // The owner must detach the world and call shutdown on the producer thread.
    // Never call game destructors from a foreign thread or after DLL teardown.
    // If that contract is violated, leak retained native objects instead of UAF.
}

bool DeferredCommandQueue::on_producer() const noexcept {
    return abi_.current_thread && abi_.current_thread(abi_.context) == producer_thread_;
}

bool DeferredCommandQueue::gates_open() const noexcept {
    return abi_.valid() && epoch_ && producer_thread_ &&
        gates_.build_fingerprint_verified && gates_.producer_thread_pump_verified &&
        gates_.completion_observer_verified && gates_.maintenance_while_paused_verified;
}

DeferredStatus DeferredCommandQueue::fail(DeferredStatus status) noexcept {
    halted_ = true;
    return status;
}

DeferredCommandQueue::Slot* DeferredCommandQueue::find(std::uint64_t id) noexcept {
    for (auto& slot : slots_)
        if (slot.state != State::empty && slot.result.id == id) return &slot;
    return nullptr;
}

DeferredStatus DeferredCommandQueue::capture(const NativeCapture& c) noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    if (halted_) return DeferredStatus::halted;
    if (!gates_open()) return fail(DeferredStatus::gates_closed);
    if (!on_producer()) return fail(DeferredStatus::wrong_thread);
    if (!c.id || c.epoch != epoch_ || !c.command_list || !c.command ||
        !c.callback || !c.weak || !c.result || !c.caller_discards_result ||
        !c.full_intent_serialized || !c.intent_durably_accepted || !c.source_layout_validated ||
        !disjoint_sources(c))
        return fail(DeferredStatus::bad_capture);
    if (c.id <= highest_id_) return fail(DeferredStatus::duplicate_id);
    Slot* free = nullptr;
    for (auto& slot : slots_) if (slot.state == State::empty) { free = &slot; break; }
    if (!free) return fail(DeferredStatus::full);

    // All fallible checks precede the first move. Native ABI moves are required
    // noexcept and consume their source; no pointer-bearing object is memcpy'd.
    abi_.move_command(abi_.context, free->command.data(), c.command);
    abi_.move_function(abi_.context, free->callback.data(), c.callback);
    abi_.move_weak(abi_.context, free->weak.data(), c.weak);
    free->owns_arguments = true;
    free->command_list = c.command_list;
    free->result = {c.id, 0, 0, false, -1};
    free->state = State::captured;
    highest_id_ = c.id;
    // Only whitelisted call sites may receive this empty discarded handle.
    // The detour relay must also return c.result in RAX (Add's actual ABI).
    std::memset(c.result, 0, sizeof(void*));
    return DeferredStatus::accepted;
}

DeferredStatus DeferredCommandQueue::grant(std::uint64_t id, std::uint64_t order,
    std::uint64_t boundary) noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    if (halted_) return DeferredStatus::halted;
    auto* slot = find(id);
    if (!slot) return fail(DeferredStatus::unknown_id);
    if (slot->state == State::granted && slot->result.order == order &&
        slot->result.boundary == boundary) return DeferredStatus::granted;
    if (slot->state != State::captured || order < next_order_ || !order)
        return fail(DeferredStatus::invalid_order);
    for (const auto& other : slots_) {
        if (&other == slot || other.state == State::empty || !other.result.order) continue;
        if (other.result.order == order) return fail(DeferredStatus::invalid_order);
        if ((other.result.order < order && other.result.boundary > boundary) ||
            (other.result.order > order && other.result.boundary < boundary))
            return fail(DeferredStatus::wrong_boundary);
    }
    if (boundary < last_boundary_) return fail(DeferredStatus::wrong_boundary);
    slot->result.order = order;
    slot->result.boundary = boundary;
    slot->state = State::granted;
    return DeferredStatus::granted;
}

DeferredStatus DeferredCommandQueue::drain(std::uint64_t boundary) noexcept {
    bool submitted_any = false;
    for (;;) {
        Slot* slot = nullptr;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            if (halted_) return DeferredStatus::halted;
            if (!gates_open()) return fail(DeferredStatus::gates_closed);
            if (!on_producer()) return fail(DeferredStatus::wrong_thread);
            if (boundary < last_boundary_) return fail(DeferredStatus::wrong_boundary);
            last_boundary_ = boundary;
            for (auto& candidate : slots_)
                if (candidate.state == State::granted && candidate.result.order == next_order_) {
                    slot = &candidate; break;
                }
            if (!slot || slot->result.boundary > boundary)
                return submitted_any ? DeferredStatus::submitted : DeferredStatus::pending;
            if (slot->result.boundary != boundary) return fail(DeferredStatus::wrong_boundary);
            // Mark before Add: an ABI test / future engine can complete reentrantly.
            slot->state = State::submitting;
            slot->in_add = true;
            slot->owns_arguments = false; // Add now owns and destructs all three.
            ++next_order_;
        }
        void* result_storage = nullptr;
        void* returned = abi_.add(abi_.context, slot->result.id, slot->command_list,
            &result_storage, slot->command.data(), slot->callback.data(), slot->weak.data());
        abi_.destroy_result(abi_.context, &result_storage);
        {
            std::lock_guard<std::mutex> lock(mutex_);
            slot->in_add = false;
            if (returned != &result_storage) return fail(DeferredStatus::wrong_result_storage);
            if (slot->state == State::submitting) slot->state = State::submitted;
            if (halted_) return DeferredStatus::halted;
        }
        submitted_any = true;
    }
}

DeferredStatus DeferredCommandQueue::report_applied(std::uint64_t id,
    std::uint64_t boundary, bool success, std::int64_t entity) noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    auto* slot = find(id);
    if (!slot) return fail(DeferredStatus::unknown_id);
    if (slot->state != State::submitting && slot->state != State::submitted)
        return fail(DeferredStatus::duplicate_completion);
    if (slot->result.boundary != boundary) return fail(DeferredStatus::wrong_boundary);
    slot->result.success = success;
    slot->result.result_entity = entity;
    slot->state = State::completed;
    return success ? DeferredStatus::applied : fail(DeferredStatus::application_failed);
}

bool DeferredCommandQueue::take_result(DeferredResult& out) noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    for (auto& slot : slots_) if (slot.state == State::completed && !slot.in_add) {
        out = slot.result;
        slot.state = State::empty;
        return true;
    }
    return false;
}

void DeferredCommandQueue::halt() noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    halted_ = true;
}

bool DeferredCommandQueue::halted() const noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    return halted_;
}

std::size_t DeferredCommandQueue::pending_count() const noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    std::size_t count = 0;
    for (const auto& slot : slots_) if (slot.state != State::empty) ++count;
    return count;
}

void DeferredCommandQueue::destroy_owned(Slot& slot) noexcept {
    if (!slot.owns_arguments) return;
    abi_.destroy_command(abi_.context, slot.command.data());
    abi_.destroy_function(abi_.context, slot.callback.data());
    abi_.destroy_weak(abi_.context, slot.weak.data());
    slot.owns_arguments = false;
}

DeferredStatus DeferredCommandQueue::shutdown(bool world_detached) noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    halted_ = true;
    if (!world_detached) return DeferredStatus::world_still_live;
    if (!on_producer()) return DeferredStatus::wrong_thread;
    for (const auto& slot : slots_) if (slot.in_add) return DeferredStatus::pending;
    for (auto& slot : slots_) {
        destroy_owned(slot);
        slot.state = State::empty;
    }
    return DeferredStatus::drained;
}

#ifdef _WIN32
namespace {
template<class Fn> Fn fn(void* base, std::uintptr_t rva) noexcept {
    return reinterpret_cast<Fn>(static_cast<std::byte*>(base) + rva);
}
std::uint64_t native_thread(void*) noexcept { return GetCurrentThreadId(); }
void native_move_command(void* b, void* dst, void* src) noexcept {
    fn<void*(*)(void*, void*)>(b, 0x9d03e0)(dst, src);
}
void*& implementation(void* object) noexcept {
    return *reinterpret_cast<void**>(static_cast<std::byte*>(object) + 0x38);
}
void native_move_function(void*, void* dst, void* src) noexcept {
    implementation(dst) = nullptr;
    void* impl = implementation(src);
    if (!impl) return;
    if (impl == src) {
        auto** table = *reinterpret_cast<void***>(impl);
        implementation(dst) = reinterpret_cast<void*(*)(void*, void*)>(table[1])(impl, dst);
        // This is the same inline move + source destruction sequence as Add.
        reinterpret_cast<void(*)(void*, bool)>(table[4])(impl, false);
    } else {
        implementation(dst) = impl;
    }
    implementation(src) = nullptr;
}
void native_move_weak(void*, void* dst, void* src) noexcept {
    auto** s = static_cast<void**>(src);
    auto** d = static_cast<void**>(dst);
    d[0] = s[0]; d[1] = s[1]; s[0] = nullptr; s[1] = nullptr;
}
void native_destroy_command(void* b, void* cmd) noexcept {
    fn<void(*)(void*)>(b, 0x9d0510)(cmd);
}
void native_destroy_function(void*, void* object) noexcept {
    void* impl = implementation(object);
    if (!impl) return;
    auto** table = *reinterpret_cast<void***>(impl);
    reinterpret_cast<void(*)(void*, bool)>(table[4])(impl, impl != object);
    implementation(object) = nullptr;
}
void native_destroy_weak(void*, void* object) noexcept {
    auto** pair = static_cast<void**>(object);
    void* control = pair[1];
    pair[0] = nullptr; pair[1] = nullptr;
    if (!control) return;
    auto* weak_count = reinterpret_cast<volatile LONG*>(static_cast<std::byte*>(control) + 0xc);
    if (InterlockedDecrement(weak_count) == 0) {
        auto** table = *reinterpret_cast<void***>(control);
        reinterpret_cast<void(*)(void*)>(table[1])(control);
    }
}
void* native_add(void* b, std::uint64_t, void* list, void* out,
    void* cmd, void* cb, void* weak) noexcept {
    return fn<void*(*)(void*, void*, void*, void*, void*)>(b, 0x9d2a00)(list, out, cmd, cb, weak);
}
void native_destroy_result(void* b, void* result) noexcept {
    fn<void(*)(void*)>(b, 0x2357910)(result);
}
bool anchors_match(void* base) noexcept {
    // Static, headless evidence against the exact 35924 executable. This check
    // must run before a future hook patches Add; a trampoline binding is then
    // required instead of recursively calling the now-hooked Add entry.
    static constexpr unsigned char move[] = {0x48,0x8b,0x02,0x45,0x33,0xc0,0x4c,0x89,0x02};
    static constexpr unsigned char cb[] = {0x48,0x83,0x7b,0x38,0x00,0x75};
    static constexpr unsigned char add[] = {0x40,0x55,0x53,0x56,0x57,0x41,0x54,0x41,0x55};
    static constexpr unsigned char destroy[] = {0x40,0x53,0x48,0x83,0xec,0x20,0x48,0x8b,0xd9};
    __try {
        auto* p = static_cast<unsigned char*>(base);
        const auto* dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(p);
        if (dos->e_magic != IMAGE_DOS_SIGNATURE || dos->e_lfanew <= 0 || dos->e_lfanew > 0x1000) return false;
        const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(p + dos->e_lfanew);
        return nt->Signature == IMAGE_NT_SIGNATURE && nt->FileHeader.Machine == IMAGE_FILE_MACHINE_AMD64 &&
            nt->FileHeader.TimeDateStamp == 0x675abcc6 && nt->OptionalHeader.SizeOfImage == 0x046ce000 &&
            std::memcmp(p + 0x9d03e0, move, sizeof(move)) == 0 &&
            std::memcmp(p + 0x9d2ac6, cb, sizeof(cb)) == 0 &&
            std::memcmp(p + 0x9d2a00, add, sizeof(add)) == 0 &&
            std::memcmp(p + 0x9d0510, destroy, sizeof(destroy)) == 0;
    } __except (EXCEPTION_EXECUTE_HANDLER) { return false; }
}
} // namespace
#endif

DeferredAbi bind_build_35924_abi(void* module_base, bool exact_fingerprint_verified) noexcept {
#ifdef _WIN32
    if (module_base && exact_fingerprint_verified && anchors_match(module_base))
        return {module_base, native_thread, native_move_command, native_move_function,
            native_move_weak, native_destroy_command, native_destroy_function,
            native_destroy_weak, native_add, native_destroy_result};
#else
    (void)module_base; (void)exact_fingerprint_verified;
#endif
    return {};
}

} // namespace tf2coop::prototype
