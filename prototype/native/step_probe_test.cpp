#include "step_probe.h"
#include <cassert>
#include <atomic>
#include <cstdio>
#include <thread>

struct World { uint64_t ticks=0, maintenance=0, us=0; int speed=3; };
static std::atomic<bool> admitted{false}, allowFinish{true};
static bool blockBody = false;
static bool nativeSites = false;
extern "C" int ProbeFakeFirstRead(void*);
extern "C" int ProbeFakeSecondRead(void*);
extern "C" char ProbeFakeFirstReturn;
extern "C" char ProbeFakeSecondReturn;
static int OriginalSpeed(void* p) { return static_cast<World*>(p)->speed; }
static uint64_t OriginalClock(void* p) { return static_cast<World*>(p)->us / 1000; }
static bool EmissionMapAccepts(uint64_t frameUs) {
    // Independent regression fixture of the actual executable's conversion and
    // EmissionMap.cpp:428 precondition. The old 100000 us hook fails this check.
    const float dt = static_cast<float>(frameUs / 1000) * .001f;
    return dt >= .2f;
}
static void FakeStep(void* p, uint64_t dt, int mode) {
    auto& w = *static_cast<World*>(p);
    assert(mode == 73);
    assert(EmissionMapAccepts(dt)); // Also guard the frame argument during HOLD.
    const int speed = nativeSites ? ProbeFakeFirstRead(p) : TF2StepProbe_TestSpeed(p, 1);
    ++w.maintenance; // Real paused Step is not a completely neutral operation.
    if (speed) {
        const int count = nativeSites ? ProbeFakeSecondRead(p) : TF2StepProbe_TestSpeed(p, 2);
        if (!nativeSites) assert(TF2StepProbe_TestSpeed(p, 0) == w.speed);
        if (blockBody) {
            admitted = true;
            while (!allowFinish.load()) std::this_thread::yield();
        }
        for (int i=0;i<count;++i) { ++w.ticks; w.us += dt; }
    }
}
static TF2ProbeStatus Status() { TF2ProbeStatus s{}; assert(!TF2StepProbe_GetStatus(&s,sizeof s)); return s; }
static void Reset(World& w) { w=World{}; TF2StepProbe_TestReset(FakeStep, OriginalSpeed, OriginalClock); }

extern "C" void ProbeFakeStep(void*,uint64_t,int);
extern "C" int ProbeFakeGetter(void*);
struct GetterValue { int ignored; int speed; };
struct GetterInput { void* ignored; GetterValue* value; uint64_t tag; };
extern "C" GetterValue* ProbeFakeLookup(GetterValue* value, uint64_t* tag) {
    assert(*tag == 0x123456789abcdef0ull); return value;
}
extern "C" void ProbeFakeBody(void* p,uint64_t dt,int mode) { FakeStep(p,dt,mode); }

int main() {
    assert(!EmissionMapAccepts(100000));
    assert(!EmissionMapAccepts(199999));
    assert(EmissionMapAccepts(200000));
    assert(EmissionMapAccepts(400000));
    World w;
    Reset(w);
    assert(Status().abi == 3 && sizeof(TF2ProbeStatus) == 144);
    assert(TF2StepProbe_Initialize(2,TF2_PROBE_STARTUP_QUIESCENT)==TF2_PROBE_BAD_ARGUMENT);
    std::atomic<bool> startArming{false};
    uint32_t armA = 99, armB = 99;
    std::thread armThreadA([&] {
        while (!startArming.load()) std::this_thread::yield();
        armA = TF2StepProbe_Arm(111);
    });
    std::thread armThreadB([&] {
        while (!startArming.load()) std::this_thread::yield();
        armB = TF2StepProbe_Arm(222);
    });
    startArming = true;
    armThreadA.join(); armThreadB.join();
    assert((armA == TF2_PROBE_OK) != (armB == TF2_PROBE_OK));
    assert(Status().epoch == (armA == TF2_PROBE_OK ? 111u : 222u));
    Reset(w);
    TF2StepProbe_TestStep(&w,200000,73);
    assert(w.ticks==3 && w.us==600000); // Passive until explicitly armed.
    assert(TF2StepProbe_Arm(42)==TF2_PROBE_WORLD_ALREADY_STEPPED);
    Reset(w);
    assert(TF2StepProbe_Arm(42)==TF2_PROBE_OK);
    for (int i=0;i<50;++i) TF2StepProbe_TestStep(&w,200000,73);
    assert(w.ticks==0 && w.maintenance==50 && Status().hold_calls==50);
    assert(TF2StepProbe_Permit(41,1,200000)==TF2_PROBE_WRONG_EPOCH);
    assert(TF2StepProbe_Permit(42,1,100000)==TF2_PROBE_BAD_ARGUMENT);
    assert(TF2StepProbe_Permit(42,1,199999)==TF2_PROBE_BAD_ARGUMENT);
    assert(TF2StepProbe_Permit(42,1,400000)==TF2_PROBE_BAD_ARGUMENT);
    assert(Status().pending_state==0 && Status().completed_frame==0 && w.ticks==0);
    assert(TF2StepProbe_Permit(42,2,200000)==TF2_PROBE_FRAME_ORDER);
    assert(TF2StepProbe_Permit(42,1,200000)==TF2_PROBE_OK);
    assert(TF2StepProbe_Permit(42,1,200000)==TF2_PROBE_DUPLICATE);
    TF2StepProbe_TestStep(&w,200000,73);
    assert(w.ticks==1 && w.us==200000 && w.speed==3);
    assert(Status().time_after_ms-Status().time_before_ms==200);
    assert(TF2StepProbe_Permit(42,1,200000)==TF2_PROBE_DUPLICATE);
    assert(TF2StepProbe_Permit(42,1,0)==TF2_PROBE_FRAME_ORDER);
    assert(TF2StepProbe_Permit(42,2,0)==TF2_PROBE_OK);
    TF2StepProbe_TestStep(&w,200000,73);
    assert(w.ticks==1 && Status().completed_frame==2 && Status().pause_permits==1);
    assert(TF2StepProbe_Permit(42,3,200000)==TF2_PROBE_OK);
    assert(TF2StepProbe_Halt(42)==TF2_PROBE_OK);
    for (int i=0;i<50;++i) TF2StepProbe_TestStep(&w,200000,73);
    assert(w.ticks==1 && Status().completed_frame==2);
    assert(TF2StepProbe_Permit(42,3,200000)==TF2_PROBE_HALTED);

    // Halt during an admitted step allows that step to finish, then stays held.
    Reset(w); blockBody=true; allowFinish=false; admitted=false;
    assert(!TF2StepProbe_Arm(7)); assert(!TF2StepProbe_Permit(7,1,200000));
    std::thread simulation([&] {TF2StepProbe_TestStep(&w,200000,73);});
    while (!admitted.load()) std::this_thread::yield();
    assert(!TF2StepProbe_Halt(7)); allowFinish=true; simulation.join(); blockBody=false;
    assert(w.ticks==1 && Status().completed_frame==1);
    TF2StepProbe_TestStep(&w,200000,73); assert(w.ticks==1);

    // Real producer/consumer racing: no repeated frame, skipped frame or step
    // from HOLD despite differently paced outer calls.
    Reset(w); assert(!TF2StepProbe_Arm(8));
    constexpr uint64_t n=10000;
    std::atomic<bool> done{false};
    std::thread sim([&] {
        while (!done.load()) TF2StepProbe_TestStep(&w,200000,73);
    });
    for (uint64_t i=1;i<=n;++i) {
        uint32_t r;
        do { r=TF2StepProbe_Permit(8,i,i%4 ? 200000 : 0); if(r==TF2_PROBE_BUSY) std::this_thread::yield(); }
        while (r==TF2_PROBE_BUSY);
        assert(r==TF2_PROBE_OK);
        while (Status().completed_frame<i) std::this_thread::yield();
    }
    done=true; sim.join();
    assert(w.ticks==7500 && w.us==1500000000 && !Status().fault);

    // A changed/unexpected engine traversal is permanently halted and never
    // acknowledged to the coordinator as a successfully completed permit.
    TF2StepProbe_TestReset([](void*,uint64_t,int){}, OriginalSpeed, OriginalClock);
    assert(!TF2StepProbe_Arm(11)); assert(!TF2StepProbe_Permit(11,1,200000));
    TF2StepProbe_TestStep(&w,200000,73);
    assert(Status().halted && Status().fault==TF2_PROBE_UNEXPECTED_SPEED_READ);
    assert(Status().completed_frame==0 && Status().completed_permits==0);

    Reset(w);
    TF2StepProbe_TestReset([](void* p,uint64_t dt,int mode) {
        FakeStep(p,dt,mode);
        static_cast<World*>(p)->us += 1000; // Unexpected advancement during HOLD.
    }, OriginalSpeed, OriginalClock);
    assert(!TF2StepProbe_Arm(12));
    TF2StepProbe_TestStep(&w,200000,73);
    assert(Status().halted && Status().fault==TF2_PROBE_CLOCK_MISMATCH);
    assert(Status().time_before_ms==0 && Status().time_after_ms==1);

    // Exercise the actual native detour/trampoline and rel32-call relocation.
    // These stand-ins carry the same stolen prologues as the real game.
    Reset(w);
    GetterValue v{0,6}; GetterInput input{nullptr,&v,0x123456789abcdef0ull};
    assert(ProbeFakeGetter(&input)==6);
    assert(TF2StepProbe_TestInstallStandins(reinterpret_cast<void*>(&ProbeFakeStep),
                                          reinterpret_cast<void*>(&ProbeFakeGetter)));
    assert(ProbeFakeGetter(&input)==6); // Relocated getter preserves call args.
    TF2StepProbe_TestReadSites(&ProbeFakeFirstReturn,&ProbeFakeSecondReturn);
    nativeSites=true;
    assert(!TF2StepProbe_Arm(9));
    ProbeFakeStep(&w,200000,73); // HOLD reaches both ABI detours.
    assert(w.ticks==0 && w.maintenance==1 && !Status().fault);
    assert(!TF2StepProbe_Permit(9,1,200000));
    ProbeFakeStep(&w,200000,73); // One inner step, original mode/this intact.
    assert(w.ticks==1 && w.us==200000 && Status().completed_frame==1 && !Status().fault);
    assert(ProbeFakeGetter(&input)==6); // Non-Step getter still unaffected.
    assert(!TF2StepProbe_Halt(9));
    ProbeFakeStep(&w,200000,73);
    assert(w.ticks==1 && w.maintenance==3 && !Status().fault);
    std::puts("step probe ABI 3: actual-engine minimum .2f regression, 200 ms advance/HOLD/pause, ordering/halt, 10000 race permits and native ABI stand-ins passed");
}
