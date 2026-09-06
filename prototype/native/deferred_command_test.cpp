#include "deferred_command.h"

#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <vector>

using namespace tf2coop::prototype;

#define CHECK(condition) do { if (!(condition)) { std::cerr << __LINE__ << ": " #condition "\n"; std::abort(); } } while (false)

namespace {
struct Token { int value; };
struct Function { Token* token; int* calls; };
struct Engine {
    struct Work {
        alignas(16) std::byte command[0x38]{};
        alignas(16) std::byte callback[0x40]{};
        alignas(16) std::byte weak[0x10]{};
    };
    std::uint64_t thread = 7;
    int live = 0;
    int callbacks = 0;
    int result_destroyed = 0;
    bool wrong_result = false;
    bool synchronous = false;
    bool take_during_add = false;
    DeferredCommandQueue* queue = nullptr;
    std::map<std::uint64_t, Work> work;
    std::vector<std::uint64_t> submitted;
    Token* token(int n) { ++live; return new Token{n}; }
    void erase(Token* p) { if (p) { --live; delete p; } }
    static Engine& self(void* p) { return *static_cast<Engine*>(p); }
    static Token*& cmd(void* p) { return *static_cast<Token**>(p); }
    static Function*& impl(void* p) {
        return *reinterpret_cast<Function**>(static_cast<std::byte*>(p) + 0x38);
    }
    static std::uint64_t current(void* p) noexcept { return self(p).thread; }
    static void move_cmd(void*, void* d, void* s) noexcept { cmd(d) = cmd(s); cmd(s) = nullptr; }
    static void move_func(void*, void* d, void* s) noexcept {
        auto* old = impl(s);
        if (old == s) {
            *static_cast<Function*>(d) = *old;
            old->token = nullptr;
            impl(d) = static_cast<Function*>(d);
        } else impl(d) = old;
        impl(s) = nullptr;
    }
    static void move_weak(void*, void* d, void* s) noexcept {
        auto** dst = static_cast<Token**>(d);
        auto** src = static_cast<Token**>(s);
        dst[0] = src[0]; dst[1] = src[1]; src[0] = src[1] = nullptr;
    }
    static void destroy_cmd(void* p, void* c) noexcept { self(p).erase(cmd(c)); cmd(c) = nullptr; }
    static void destroy_func(void* p, void* c) noexcept {
        auto* f = impl(c);
        if (f) {
            self(p).erase(f->token);
            if (f != c) delete f;
            impl(c) = nullptr;
        }
    }
    static void destroy_weak(void* p, void* c) noexcept {
        auto** pair = static_cast<Token**>(c);
        self(p).erase(pair[1]); pair[0] = pair[1] = nullptr;
    }
    static void* add(void* p, std::uint64_t id, void*, void* out, void* c,
        void* cb, void* weak) noexcept {
        auto& e = self(p);
        auto& w = e.work[id];
        move_cmd(p, w.command, c); move_func(p, w.callback, cb); move_weak(p, w.weak, weak);
        // Add consumes the now-empty by-value argument objects too.
        destroy_cmd(p, c); destroy_func(p, cb); destroy_weak(p, weak);
        *static_cast<Token**>(out) = e.token(99);
        e.submitted.push_back(id);
        if (e.synchronous) {
            e.finish(id, 0, true);
            DeferredResult result;
            e.take_during_add = e.queue->take_result(result);
        }
        return e.wrong_result ? nullptr : out;
    }
    static void destroy_out(void* p, void* out) noexcept {
        auto& e = self(p); e.erase(cmd(out)); cmd(out) = nullptr; ++e.result_destroyed;
    }
    DeferredAbi abi() {
        return {this,current,move_cmd,move_func,move_weak,destroy_cmd,destroy_func,
            destroy_weak,add,destroy_out};
    }
    void finish(std::uint64_t id, std::uint64_t boundary, bool success) {
        auto it = work.find(id); CHECK(it != work.end());
        auto& w = it->second;
        if (auto* f = impl(w.callback)) { CHECK(f->token); ++*f->calls; }
        CHECK(queue->report_applied(id, boundary, success, success ? 1000 + static_cast<std::int64_t>(id) : -1)
            == (success ? DeferredStatus::applied : DeferredStatus::application_failed));
        destroy_cmd(this,w.command); destroy_func(this,w.callback); destroy_weak(this,w.weak);
        work.erase(it);
    }
    void world_detach() {
        for (auto& item : work) {
            destroy_cmd(this,item.second.command); destroy_func(this,item.second.callback);
            destroy_weak(this,item.second.weak);
        }
        work.clear();
    }
};

struct Call {
    alignas(16) std::byte command[0x38]{};
    alignas(16) std::byte callback[0x40]{};
    alignas(16) std::byte weak[0x10]{};
    void* result = reinterpret_cast<void*>(0x1234);
    Engine& engine;
    explicit Call(Engine& e, bool heap = false) : engine(e) {
        Engine::cmd(command) = e.token(1);
        auto* f = heap ? new Function{} : reinterpret_cast<Function*>(callback);
        f->token = e.token(2); f->calls = &e.callbacks; Engine::impl(callback) = f;
        auto** pair = reinterpret_cast<Token**>(weak); pair[1] = e.token(3);
    }
    ~Call() {
        Engine::destroy_cmd(&engine,command); Engine::destroy_func(&engine,callback);
        Engine::destroy_weak(&engine,weak);
    }
    NativeCapture capture(std::uint64_t id) {
        return {id,42,&engine,command,callback,weak,&result,true,true,true,true};
    }
    bool untouched() { return Engine::cmd(command) && Engine::impl(callback) && result == reinterpret_cast<void*>(0x1234); }
};
DeferredGates open() { return {true,true,true,true}; }
void cleanup(DeferredCommandQueue& queue, Engine& e) {
    e.thread = 7; e.world_detach();
    CHECK(queue.shutdown(true) == DeferredStatus::drained);
}

void ownership_and_real_callback(bool heap) {
    Engine e;
    DeferredCommandQueue q(e.abi(),open(),42,7); e.queue = &q;
    {
        Call c(e,heap);
        CHECK(q.capture(c.capture(1)) == DeferredStatus::accepted);
        CHECK(!Engine::cmd(c.command) && !Engine::impl(c.callback) && !c.result);
        CHECK(q.drain(0) == DeferredStatus::pending);
        CHECK(e.callbacks == 0 && e.submitted.empty());
    } // caller stack expires before its command is submitted
    CHECK(e.live == 3);
    CHECK(q.grant(1,1,0) == DeferredStatus::granted);
    CHECK(q.drain(0) == DeferredStatus::submitted);
    CHECK(e.callbacks == 0 && e.live == 3 && e.result_destroyed == 1);
    e.finish(1,0,true);
    CHECK(e.callbacks == 1 && e.live == 0);
    DeferredResult r; CHECK(q.take_result(r));
    CHECK(r.id == 1 && r.order == 1 && r.boundary == 0 && r.success && r.result_entity == 1001);
    CHECK(!q.take_result(r)); cleanup(q,e);
}

void missing_gates_and_bad_capture() {
    for (int which = 0; which < 8; ++which) {
        Engine e;
        auto gates = open();
        if (which == 0) gates.build_fingerprint_verified = false;
        if (which == 1) gates.producer_thread_pump_verified = false;
        if (which == 2) gates.completion_observer_verified = false;
        if (which == 3) gates.maintenance_while_paused_verified = false;
        DeferredCommandQueue q(e.abi(),gates,42,7); e.queue = &q;
        {
            Call c(e); auto request = c.capture(1);
            if (which == 4) request.caller_discards_result = false;
            if (which == 5) request.full_intent_serialized = false;
            if (which == 6) request.intent_durably_accepted = false;
            if (which == 7) request.source_layout_validated = false;
            CHECK(q.capture(request) == (which < 4 ? DeferredStatus::gates_closed : DeferredStatus::bad_capture));
            CHECK(c.untouched() && q.halted());
            CHECK(q.capture(request) == DeferredStatus::halted);
        }
        CHECK(e.live == 0); cleanup(q,e);
    }
}

void order_and_boundary() {
    Engine e; DeferredCommandQueue q(e.abi(),open(),42,7); e.queue = &q;
    { Call a(e); Call b(e,true);
      CHECK(q.capture(a.capture(1)) == DeferredStatus::accepted);
      CHECK(q.capture(b.capture(2)) == DeferredStatus::accepted); }
    CHECK(q.grant(2,2,5) == DeferredStatus::granted);
    CHECK(q.drain(5) == DeferredStatus::pending);
    CHECK(q.grant(1,1,5) == DeferredStatus::granted);
    CHECK(q.grant(1,1,5) == DeferredStatus::granted); // idempotent network replay
    CHECK(q.drain(5) == DeferredStatus::submitted);
    CHECK((e.submitted == std::vector<std::uint64_t>{1,2}));
    e.finish(2,5,true); e.finish(1,5,true); // asynchronous completion order
    CHECK(e.callbacks == 2 && e.live == 0); cleanup(q,e);
}

void wrong_thread_and_stale_boundary() {
    for (bool wrong_thread : {false,true}) {
        Engine e; DeferredCommandQueue q(e.abi(),open(),42,7); e.queue = &q;
        { Call c(e); CHECK(q.capture(c.capture(1)) == DeferredStatus::accepted); }
        CHECK(q.grant(1,1,3) == DeferredStatus::granted);
        if (wrong_thread) e.thread = 8;
        CHECK(q.drain(wrong_thread ? 3 : 4) == (wrong_thread ? DeferredStatus::wrong_thread : DeferredStatus::wrong_boundary));
        CHECK(e.submitted.empty() && e.callbacks == 0 && e.live == 3);
        cleanup(q,e); CHECK(e.live == 0 && e.callbacks == 0);
    }
}

void queue_full_no_source_loss() {
    Engine e; DeferredCommandQueue q(e.abi(),open(),42,7); e.queue = &q;
    for (std::size_t id = 1; id <= q.capacity; ++id) {
        Call c(e,id % 2 == 0); CHECK(q.capture(c.capture(id)) == DeferredStatus::accepted);
    }
    { Call c(e); CHECK(q.capture(c.capture(33)) == DeferredStatus::full); CHECK(c.untouched()); }
    CHECK(q.pending_count() == q.capacity && e.submitted.empty());
    cleanup(q,e); CHECK(e.live == 0);
}

void errors_stop_later_work() {
    Engine e; DeferredCommandQueue q(e.abi(),open(),42,7); e.queue = &q;
    { Call c(e); CHECK(q.capture(c.capture(1)) == DeferredStatus::accepted); }
    CHECK(q.grant(1,1,2) == DeferredStatus::granted);
    CHECK(q.drain(2) == DeferredStatus::submitted);
    e.finish(1,2,false);
    CHECK(q.halted()); DeferredResult r; CHECK(q.take_result(r) && !r.success);
    { Call c(e); CHECK(q.capture(c.capture(2)) == DeferredStatus::halted); CHECK(c.untouched()); }
    CHECK(e.live == 0); cleanup(q,e);
}

void duplicate_and_wrong_result() {
    for (bool wrong_result : {false,true}) {
        Engine e; DeferredCommandQueue q(e.abi(),open(),42,7); e.queue = &q;
        { Call c(e); CHECK(q.capture(c.capture(1)) == DeferredStatus::accepted); }
        if (wrong_result) {
            e.wrong_result = true;
            CHECK(q.grant(1,1,0) == DeferredStatus::granted);
            CHECK(q.drain(0) == DeferredStatus::wrong_result_storage);
            CHECK(e.callbacks == 0 && e.result_destroyed == 1);
        } else {
            Call c(e); CHECK(q.capture(c.capture(1)) == DeferredStatus::duplicate_id); CHECK(c.untouched());
        }
        cleanup(q,e); CHECK(e.live == 0);
    }
}

void reentrant_completion_and_shutdown_contract() {
    Engine e; DeferredCommandQueue q(e.abi(),open(),42,7); e.queue = &q; e.synchronous = true;
    { Call c(e,true); CHECK(q.capture(c.capture(1)) == DeferredStatus::accepted); }
    CHECK(q.grant(1,1,0) == DeferredStatus::granted);
    CHECK(q.drain(0) == DeferredStatus::submitted);
    CHECK(!e.take_during_add); // no slot reuse before Add returns
    DeferredResult r; CHECK(q.take_result(r) && r.result_entity == 1001);
    CHECK(q.shutdown(false) == DeferredStatus::world_still_live);
    CHECK(e.live == 0); cleanup(q,e);
}

void aliased_sources_and_conflicting_grants() {
    {
        Engine e; DeferredCommandQueue q(e.abi(),open(),42,7); e.queue = &q;
        { Call c(e); auto request = c.capture(1); request.result = c.callback;
          CHECK(q.capture(request) == DeferredStatus::bad_capture); CHECK(c.untouched()); }
        CHECK(e.live == 0); cleanup(q,e);
    }
    {
        Engine e; DeferredCommandQueue q(e.abi(),open(),42,7); e.queue = &q;
        { Call a(e); Call b(e);
          CHECK(q.capture(a.capture(1)) == DeferredStatus::accepted);
          CHECK(q.capture(b.capture(2)) == DeferredStatus::accepted); }
        CHECK(q.grant(2,2,3) == DeferredStatus::granted);
        CHECK(q.grant(1,1,4) == DeferredStatus::wrong_boundary);
        CHECK(e.submitted.empty()); cleanup(q,e); CHECK(e.live == 0);
    }
}
} // namespace

int main() {
    CHECK(!bind_build_35924_abi(nullptr,false).valid());
    ownership_and_real_callback(false); ownership_and_real_callback(true);
    missing_gates_and_bad_capture(); order_and_boundary(); wrong_thread_and_stale_boundary();
    queue_full_no_source_loss(); errors_stop_later_work(); duplicate_and_wrong_result();
    reentrant_completion_and_shutdown_contract();
    aliased_sources_and_conflicting_grants();
    std::cout << "Deferred command adapter: 20 scenarios passed (fake engine ABI; no game hooked).\n";
}
