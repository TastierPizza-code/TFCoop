#include "probe_runtime.h"
#include <windows.h>
#include <atomic>
#include <cstring>
#include <cwchar>
#include <sstream>
#include <string>
#include <locale>

namespace {
constexpr size_t MAX_RECORD = 4096;
// CRT/Lua io.open readers on Windows need not grant FILE_SHARE_DELETE. Their
// short read can deny a rename even though all file contents are valid. Retry
// only that atomic replacement, never truncate the published status file.
constexpr ULONGLONG IO_CONTENTION_RETRY_MS = 250;
constexpr DWORD IO_CONTENTION_RETRY_SLEEP_MS = 5;
enum class IoOperation : uint32_t {
    None=0, ControlOpen=1, ControlSize=2, ControlRead=3,
    StatusOpen=4, StatusWrite=5, StatusFlush=6, StatusReplace=7,
};
enum class Action { Permit, Halt };
struct Request {
    uint64_t epoch=0, id=0, frame=0;
    uint32_t dt=0;
    Action action=Action::Permit;
    bool operator==(const Request& b) const {
        return epoch==b.epoch && id==b.id && frame==b.frame && dt==b.dt && action==b.action;
    }
};
struct Runtime {
    std::wstring directory, controlPath, statusPath, temporaryPath;
    uint64_t epoch=0, received=0, acknowledged=0, completed=0;
    uint32_t result=0, runtimeFault=0, win32Error=0, completedDt=0;
    Request last;
    bool haveRequest=false, waitingSubmit=false, terminalHalt=false, sawControl=false;
    HANDLE stopEvent=nullptr, worker=nullptr;
    std::string previousStatus;
    uint64_t lastPublished=0;
    uint64_t statusReplaceRetries=0;
    DWORD statusLastRetryError=0;
    uint64_t controlOpenRetries=0;
    DWORD controlLastRetryError=0;
    IoOperation ioOperation=IoOperation::None;
};
Runtime runtime;
std::atomic<uint32_t> lifecycle{0}; // 0 never started, 1 starting, 2 running, 3 stopping, 4 stopped.
std::atomic_flag controlGate = ATOMIC_FLAG_INIT;
#ifdef TF2_STEP_PROBE_TEST
std::atomic<uint64_t> observedStatusContentions{0}, observedControlContentions{0};
#endif

struct ControlClaim {
    bool acquired;
    ControlClaim() : acquired(!controlGate.test_and_set(std::memory_order_acquire)) {}
    ~ControlClaim() { if (acquired) controlGate.clear(std::memory_order_release); }
};

void LatchFailure(uint32_t reason, DWORD win32=0, IoOperation operation=IoOperation::None) {
    if (!runtime.runtimeFault) {
        runtime.runtimeFault=reason;
        runtime.win32Error=win32;
        runtime.ioOperation=operation;
    }
    runtime.result=reason;
    runtime.waitingSubmit=false;
    TF2StepProbe_Halt(runtime.epoch);
}

bool Decimal(const std::string& s, uint64_t& value) {
    if (s.empty() || s.size()>20) return false;
    value=0;
    for (unsigned char c : s) {
        if (c<'0' || c>'9') return false;
        const uint64_t digit=c-'0';
        if (value>(UINT64_MAX-digit)/10) return false;
        value=value*10+digit;
    }
    return true;
}

bool Parse(const std::string& text, Request& request) {
    if (text.empty() || text.size()>MAX_RECORD || text.back()!='\n') return false;
    unsigned seen=0;
    size_t begin=0;
    while (begin<text.size()) {
        const size_t end=text.find('\n',begin);
        if (end==std::string::npos) return false;
        std::string line=text.substr(begin,end-begin);
        begin=end+1;
        if (!line.empty() && line.back()=='\r') line.pop_back();
        const size_t equals=line.find('=');
        if (equals==std::string::npos || line.find('=',equals+1)!=std::string::npos) return false;
        const auto key=line.substr(0,equals), value=line.substr(equals+1);
        unsigned bit=0;
        uint64_t n=0;
        if (key=="action") {
            bit=8;
            if (value=="permit") request.action=Action::Permit;
            else if (value=="halt") request.action=Action::Halt;
            else return false;
        } else {
            if (!Decimal(value,n)) return false;
            if (key=="protocol") { bit=1; if (n!=1) return false; }
            else if (key=="epoch") { bit=2; request.epoch=n; }
            else if (key=="request") { bit=4; request.id=n; }
            else if (key=="frame") { bit=16; request.frame=n; }
            else if (key=="dt_us") {
                bit=32;
                if (n!=0 && n!=TF2_PROBE_STEP_US) return false;
                request.dt=static_cast<uint32_t>(n);
            } else return false;
        }
        if (seen&bit) return false;
        seen|=bit;
    }
    if ((seen&15)!=15 || !request.epoch || !request.id) return false;
    if (request.action==Action::Permit) return seen==63 && request.frame!=0;
    // Terminal halt deliberately has no sequence dependency; optional frame/dt
    // fields are accepted only as zero. It can supersede an unread permit.
    return request.frame==0 && request.dt==0;
}

bool Contended(DWORD error) {
    // ACCESS_DENIED can also mean a permanent ACL/attribute problem. The
    // deadline is therefore mandatory; it remains a terminal I/O failure.
    return error==ERROR_ACCESS_DENIED || error==ERROR_SHARING_VIOLATION ||
           error==ERROR_LOCK_VIOLATION;
}

enum class ReadResult { Missing, Empty, Record, Error, TooLarge };
ReadResult ReadControl(std::string& text, DWORD& error, IoOperation& operation) {
    operation=IoOperation::ControlOpen;
    HANDLE file=INVALID_HANDLE_VALUE;
    const ULONGLONG deadline=GetTickCount64()+IO_CONTENTION_RETRY_MS;
    while ((file=CreateFileW(runtime.controlPath.c_str(),GENERIC_READ,
            FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL,nullptr))==INVALID_HANDLE_VALUE) {
        error=GetLastError();
        if (error==ERROR_FILE_NOT_FOUND) return ReadResult::Missing;
        if (!Contended(error) || GetTickCount64()>=deadline) return ReadResult::Error;
        ++runtime.controlOpenRetries;
        runtime.controlLastRetryError=error;
#ifdef TF2_STEP_PROBE_TEST
        ++observedControlContentions;
#endif
        Sleep(IO_CONTENTION_RETRY_SLEEP_MS);
    }
    operation=IoOperation::ControlSize;
    LARGE_INTEGER size{};
    if (!GetFileSizeEx(file,&size)) { error=GetLastError(); CloseHandle(file); return ReadResult::Error; }
    if (size.QuadPart>static_cast<LONGLONG>(MAX_RECORD) || size.QuadPart<0) {
        CloseHandle(file); return ReadResult::TooLarge;
    }
    text.resize(static_cast<size_t>(size.QuadPart));
    operation=IoOperation::ControlRead;
    DWORD got=0;
    if (size.QuadPart && !ReadFile(file,&text[0],static_cast<DWORD>(size.QuadPart),&got,nullptr)) {
        error=GetLastError(); CloseHandle(file); return ReadResult::Error;
    }
    CloseHandle(file);
    if (got!=size.QuadPart) { error=ERROR_HANDLE_EOF; return ReadResult::Error; }
    error=0; operation=IoOperation::None;
    return text.empty() ? ReadResult::Empty : ReadResult::Record;
}

bool AtomicStatus(const std::string& content, DWORD& error, IoOperation& operation) {
    operation=IoOperation::StatusWrite;
    if (content.size()>MAX_RECORD) { error=ERROR_BUFFER_OVERFLOW; return false; }
    operation=IoOperation::StatusOpen;
    HANDLE file=CreateFileW(runtime.temporaryPath.c_str(),GENERIC_WRITE,
        FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,CREATE_ALWAYS,
        FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) { error=GetLastError(); return false; }
    operation=IoOperation::StatusWrite;
    DWORD written=0;
    const bool ok=!!WriteFile(file,content.data(),static_cast<DWORD>(content.size()),&written,nullptr);
    if (!ok || written!=content.size()) {
        error=ok ? ERROR_WRITE_FAULT : GetLastError(); CloseHandle(file); return false;
    }
    operation=IoOperation::StatusFlush;
    if (!FlushFileBuffers(file)) { error=GetLastError(); CloseHandle(file); return false; }
    CloseHandle(file);
    operation=IoOperation::StatusReplace;
    const ULONGLONG deadline=GetTickCount64()+IO_CONTENTION_RETRY_MS;
    while (!MoveFileExW(runtime.temporaryPath.c_str(),runtime.statusPath.c_str(),
                       MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH)) {
        error=GetLastError();
        if (!Contended(error) || GetTickCount64()>=deadline) return false;
        ++runtime.statusReplaceRetries;
        runtime.statusLastRetryError=error;
#ifdef TF2_STEP_PROBE_TEST
        ++observedStatusContentions;
#endif
        // Only the file worker waits. The engine hook does no I/O and cannot
        // receive another permit until this request has been published.
        Sleep(IO_CONTENTION_RETRY_SLEEP_MS);
    }
    error=0; operation=IoOperation::None;
    return true;
}

TF2ProbeStatus GateStatus() {
    TF2ProbeStatus s{};
    if (TF2StepProbe_GetStatus(&s,sizeof s)!=TF2_PROBE_OK) {
        s.halted=1; s.fault=TF2_RUNTIME_INTERNAL_ERROR;
    }
    return s;
}

void UpdateCompletion(const TF2ProbeStatus& s) {
    if (runtime.haveRequest && runtime.last.action==Action::Permit &&
        runtime.acknowledged==runtime.last.id && !s.halted && !s.fault &&
        !runtime.runtimeFault && s.pending_state==0 && s.completed_frame==runtime.last.frame) {
        runtime.completed=runtime.last.id;
        runtime.completedDt=runtime.last.dt;
    }
}

std::string StatusText(const TF2ProbeStatus& s) {
    const bool ready=lifecycle.load()==2 && s.initialized && s.armed &&
                     !s.halted && !s.fault && !runtime.runtimeFault;
    std::ostringstream out;
    out.imbue(std::locale::classic());
    out << "protocol=1\nabi=" << s.abi << "\nnative_step_us=" << TF2_PROBE_STEP_US
        << "\nepoch=" << runtime.epoch
        << "\nready=" << unsigned(ready)
        << "\nrequest_received=" << runtime.received
        << "\nrequest_acknowledged=" << runtime.acknowledged
        << "\nrequest_completed=" << runtime.completed
        << "\nresult=" << runtime.result
        << "\nruntime_fault=" << runtime.runtimeFault
        << "\nwin32_error=" << runtime.win32Error
        << "\nio_operation=" << static_cast<uint32_t>(runtime.ioOperation)
        << "\nstatus_replace_retries=" << runtime.statusReplaceRetries
        << "\nstatus_last_retry_error=" << runtime.statusLastRetryError
        << "\ncontrol_open_retries=" << runtime.controlOpenRetries
        << "\ncontrol_last_retry_error=" << runtime.controlLastRetryError
        << "\ninitialized=" << s.initialized << "\narmed=" << s.armed
        << "\nhalted=" << s.halted << "\nfault=" << s.fault
        << "\nprobe_required=1\npending_state=" << s.pending_state
        << "\ncompleted_frame=" << s.completed_frame
        << "\npending_frame=" << s.pending_frame
        << "\npending_dt_us=" << s.pending_dt_us
        << "\ncompleted_dt_us=" << runtime.completedDt
        << "\nouter_calls=" << s.outer_calls << "\nhold_calls=" << s.hold_calls
        << "\nadvance_permits=" << s.advance_permits << "\npause_permits=" << s.pause_permits
        << "\ncompleted_permits=" << s.completed_permits
        << "\nfirst_speed_reads=" << s.first_speed_reads
        << "\nsecond_speed_reads=" << s.second_speed_reads
        << "\noriginal_frame_time_us=" << s.original_frame_time_us
        << "\ntime_before_ms=" << s.time_before_ms << "\ntime_after_ms=" << s.time_after_ms << '\n';
    return out.str();
}

bool Publish(bool force=false) {
    const auto s=GateStatus();
    UpdateCompletion(s);
    const std::string snapshot=StatusText(s);
    const uint64_t now=GetTickCount64();
    if (!force && snapshot==runtime.previousStatus && now-runtime.lastPublished<1000) return true;
    DWORD error=0;
    IoOperation operation=IoOperation::None;
    const std::string content=snapshot+"updated_ms="+std::to_string(now)+"\n";
    if (!AtomicStatus(content,error,operation)) {
        LatchFailure(TF2_RUNTIME_IO_ERROR,error,operation); return false;
    }
    runtime.previousStatus=snapshot;
    runtime.lastPublished=now;
    return true;
}

void Submit() {
    const auto& r=runtime.last;
    const uint32_t result=TF2StepProbe_Permit(r.epoch,r.frame,r.dt);
    runtime.result=result;
    runtime.waitingSubmit=result==TF2_PROBE_BUSY;
    if (result==TF2_PROBE_OK || result==TF2_PROBE_DUPLICATE) runtime.acknowledged=r.id;
    else if (!runtime.waitingSubmit) LatchFailure(result);
}

void Accept(const Request& r) {
    if (r.epoch!=runtime.epoch) { LatchFailure(TF2_PROBE_WRONG_EPOCH); return; }
    if (r.action==Action::Halt) {
        // This exception is intentionally terminal: a lost/unread permit may
        // never prevent a user or a coordinator timeout from stopping the gate.
        runtime.received=r.id; runtime.last=r; runtime.haveRequest=true;
        runtime.waitingSubmit=false; runtime.terminalHalt=true;
        runtime.result=TF2StepProbe_Halt(r.epoch);
        if (runtime.result==TF2_PROBE_OK) {
            runtime.acknowledged=r.id; runtime.completed=r.id;
        }
        return;
    }
    if (runtime.terminalHalt || runtime.runtimeFault) {
        runtime.result=TF2_PROBE_HALTED; return;
    }
    if (runtime.haveRequest && r.id==runtime.last.id) {
        if (!(r==runtime.last)) LatchFailure(TF2_RUNTIME_REQUEST_CONFLICT);
        else if (runtime.waitingSubmit) Submit();
        return;
    }
    if (r.id!=runtime.received+1 || runtime.waitingSubmit) {
        LatchFailure(TF2_RUNTIME_REQUEST_ORDER); return;
    }
    runtime.received=r.id; runtime.last=r; runtime.haveRequest=true;
    Submit();
}

DWORD WINAPI Worker(void*) {
    try {
        while (WaitForSingleObject(runtime.stopEvent,10)==WAIT_TIMEOUT) {
            std::string text;
            DWORD error=0;
            IoOperation operation=IoOperation::None;
            const auto result=ReadControl(text,error,operation);
            if (result==ReadResult::Record) {
                runtime.sawControl=true;
                Request request;
                if (!Parse(text,request)) LatchFailure(TF2_RUNTIME_BAD_RECORD);
                else Accept(request);
            } else if (result==ReadResult::TooLarge) LatchFailure(TF2_RUNTIME_BAD_RECORD);
            else if (result==ReadResult::Error ||
                     (result==ReadResult::Missing && runtime.sawControl)) {
                LatchFailure(TF2_RUNTIME_IO_ERROR,error,operation);
            }
            // Empty/missing initial mailbox cannot release a simulation step.
            // There is no timeout release. I/O failures remain terminal even
            // if a later retry can publish the diagnostic file successfully.
            Publish();
        }
        TF2StepProbe_Halt(runtime.epoch);
        Publish(true);
    } catch (...) {
        LatchFailure(TF2_RUNTIME_INTERNAL_ERROR);
        try { Publish(true); } catch (...) {}
    }
    lifecycle.store(4,std::memory_order_release);
    return 0;
}

bool AbsoluteDirectory(const wchar_t* input, std::wstring& output) {
    if (!input) return false;
    const size_t n=wcsnlen_s(input,32768);
    if (!n || n>=32768) return false;
    const bool drive=n>=3 && ((input[0]>=L'a'&&input[0]<=L'z') || (input[0]>=L'A'&&input[0]<=L'Z')) &&
        input[1]==L':' && (input[2]==L'\\'||input[2]==L'/');
    const bool unc=n>=3 && input[0]==L'\\' && input[1]==L'\\';
    if (!drive && !unc) return false;
    const DWORD needed=GetFullPathNameW(input,0,nullptr,nullptr);
    if (!needed || needed>32700) return false;
    output.resize(needed);
    const DWORD got=GetFullPathNameW(input,needed,&output[0],nullptr);
    if (!got || got>=needed) return false;
    output.resize(got);
    const DWORD attributes=GetFileAttributesW(output.c_str());
    if (attributes==INVALID_FILE_ATTRIBUTES || !(attributes&FILE_ATTRIBUTE_DIRECTORY)) return false;
    if (output.back()!=L'\\' && output.back()!=L'/') output.push_back(L'\\');
    return true;
}
} // namespace

TF2_PROBE_API uint32_t TF2StepProbe_RuntimeStart(
    const wchar_t* absolute_session_dir, uint64_t epoch, uint32_t startup_quiescent) {
    ControlClaim claim;
    if (!claim.acquired) return TF2_PROBE_BUSY;
    if (!epoch) return TF2_PROBE_BAD_ARGUMENT;
    if (startup_quiescent!=TF2_PROBE_STARTUP_QUIESCENT) return TF2_PROBE_STARTUP_NOT_QUIESCENT;
    std::wstring directory;
    if (!AbsoluteDirectory(absolute_session_dir,directory)) return TF2_RUNTIME_BAD_DIRECTORY;
    if (lifecycle.load()) {
        if (lifecycle.load()==2 && runtime.epoch==epoch && runtime.directory==directory)
            return TF2_PROBE_DUPLICATE;
        return TF2_PROBE_ALREADY_ARMED;
    }
    lifecycle=1;
    runtime.directory=directory; runtime.epoch=epoch;
    runtime.controlPath=directory+L"native_control.txt";
    runtime.statusPath=directory+L"native_status.txt";
    runtime.temporaryPath=directory+L"native_status.txt.tmp";
    if (!Publish(true)) { lifecycle=4; return TF2_RUNTIME_IO_ERROR; }
    uint32_t result=TF2StepProbe_Initialize(TF2_PROBE_ABI,startup_quiescent);
    if (result==TF2_PROBE_OK || result==TF2_PROBE_DUPLICATE) result=TF2StepProbe_Arm(epoch);
    if (result!=TF2_PROBE_OK) {
        LatchFailure(result); lifecycle=4; Publish(true); return result;
    }
    runtime.stopEvent=CreateEventW(nullptr,TRUE,FALSE,nullptr);
    if (!runtime.stopEvent) {
        LatchFailure(TF2_RUNTIME_THREAD_ERROR,GetLastError()); lifecycle=4; Publish(true);
        return TF2_RUNTIME_THREAD_ERROR;
    }
    lifecycle=2;
    runtime.worker=CreateThread(nullptr,0,Worker,nullptr,0,nullptr);
    if (!runtime.worker) {
        LatchFailure(TF2_RUNTIME_THREAD_ERROR,GetLastError()); lifecycle=4; Publish(true);
        CloseHandle(runtime.stopEvent); runtime.stopEvent=nullptr;
        return TF2_RUNTIME_THREAD_ERROR;
    }
    return TF2_PROBE_OK;
}

TF2_PROBE_API uint32_t TF2StepProbe_RuntimeStop(uint64_t epoch) {
    ControlClaim claim;
    if (!claim.acquired) return TF2_PROBE_BUSY;
    if (!lifecycle.load()) return TF2_PROBE_NOT_INITIALIZED;
    if (epoch!=runtime.epoch) return TF2_PROBE_WRONG_EPOCH;
    TF2StepProbe_Halt(epoch);
    if (runtime.stopEvent) SetEvent(runtime.stopEvent);
    if (runtime.worker) {
        lifecycle=3;
        if (WaitForSingleObject(runtime.worker,2000)!=WAIT_OBJECT_0) return TF2_RUNTIME_STOP_TIMEOUT;
        CloseHandle(runtime.worker); runtime.worker=nullptr;
    }
    if (runtime.stopEvent) { CloseHandle(runtime.stopEvent); runtime.stopEvent=nullptr; }
    lifecycle=4;
    return TF2_PROBE_OK;
}

#ifdef TF2_STEP_PROBE_TEST
void TF2StepProbe_RuntimeTestReset() {
    if (runtime.worker || runtime.stopEvent) return;
    runtime=Runtime{};
    lifecycle=0;
    observedStatusContentions=0; observedControlContentions=0;
}
uint64_t TF2StepProbe_RuntimeTestContentions(bool control) {
    return control ? observedControlContentions.load() : observedStatusContentions.load();
}
#endif
