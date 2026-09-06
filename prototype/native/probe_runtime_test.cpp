#include "probe_runtime.h"
#include <windows.h>
#include <cassert>
#include <atomic>
#include <cstdio>
#include <string>
#include <thread>
#include <set>

struct World { uint64_t time=0, maintenance=0; };
static int Speed(void*) { return 3; }
static uint64_t Clock(void* p) { return static_cast<World*>(p)->time; }
static void Step(void* p,uint64_t us,int) {
    // Same observed downstream engine precondition as EmissionMap::Update;
    // the former 100000 us hook argument would fail here even in this fixture.
    assert(static_cast<float>(us/1000)*.001f >= .2f);
    auto& w=*static_cast<World*>(p);
    ++w.maintenance;
    if (TF2StepProbe_TestSpeed(p,1)) {
        assert(TF2StepProbe_TestSpeed(p,2)==1);
        w.time+=us/1000;
    }
}
static void Write(const std::wstring& dir,const std::string& text) {
    const std::wstring temp=dir+L"\\producer.tmp", path=dir+L"\\native_control.txt";
    HANDLE file=CreateFileW(temp.c_str(),GENERIC_WRITE,FILE_SHARE_READ|FILE_SHARE_DELETE,nullptr,
                            CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);
    assert(file!=INVALID_HANDLE_VALUE);
    DWORD written=0;
    assert(WriteFile(file,text.data(),static_cast<DWORD>(text.size()),&written,nullptr));
    assert(written==text.size()); CloseHandle(file);
    assert(MoveFileExW(temp.c_str(),path.c_str(),MOVEFILE_REPLACE_EXISTING|MOVEFILE_WRITE_THROUGH));
}
static std::string Read(const std::wstring& dir) {
    const auto path=dir+L"\\native_status.txt";
    HANDLE file=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
        nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE) return {};
    char buffer[4097]{}; DWORD got=0; assert(ReadFile(file,buffer,4096,&got,nullptr)); CloseHandle(file);
    return std::string(buffer,got);
}
static HANDLE OpenTestReader(const std::wstring& path,DWORD share) {
    HANDLE file=INVALID_HANDLE_VALUE;
    const auto deadline=GetTickCount64()+1000;
    do {
        file=CreateFileW(path.c_str(),GENERIC_READ,share,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);
        if(file!=INVALID_HANDLE_VALUE) break;
        assert(GetLastError()==ERROR_SHARING_VIOLATION || GetLastError()==ERROR_ACCESS_DENIED);
        Sleep(1);
    } while(GetTickCount64()<deadline);
    assert(file!=INVALID_HANDLE_VALUE);
    return file;
}
static HANDLE LockStatusAgainstReplacement(const std::wstring& dir) {
    return OpenTestReader(dir+L"\\native_status.txt",FILE_SHARE_READ|FILE_SHARE_WRITE);
}
static void WaitForContention(bool control) {
    const auto deadline=GetTickCount64()+3000;
    while(!TF2StepProbe_RuntimeTestContentions(control) && GetTickCount64()<deadline) Sleep(1);
    assert(TF2StepProbe_RuntimeTestContentions(control)>0);
}
static void CheckWholeSnapshot(const std::string& text) {
    assert(!text.empty() && text.size()<=4096 && text.back()=='\n');
    std::set<std::string> keys;
    size_t begin=0;
    while(begin<text.size()) {
        const size_t end=text.find('\n',begin), equals=text.find('=',begin);
        assert(end!=std::string::npos && equals!=std::string::npos && equals>begin && equals+1<end);
        assert(keys.insert(text.substr(begin,equals-begin)).second);
        for(size_t i=equals+1;i<end;++i) assert(text[i]>='0' && text[i]<='9');
        begin=end+1;
    }
    for(const auto* key:{"protocol","abi","epoch","ready","request_received",
            "request_acknowledged","request_completed","runtime_fault","completed_frame",
            "time_before_ms","time_after_ms","updated_ms"}) assert(keys.count(key));
}
static uint64_t Field(const std::string& text,const std::string& key) {
    const auto token=key+"=";
    size_t pos=text.compare(0,token.size(),token)==0 ? 0 : text.find("\n"+token);
    assert(pos!=std::string::npos);
    if(pos) ++pos;
    return std::stoull(text.substr(pos+token.size()));
}
template<class Predicate> static std::string Wait(const std::wstring& dir,Predicate predicate) {
    const auto end=GetTickCount64()+5000;
    do { const auto s=Read(dir); if(!s.empty() && predicate(s)) return s; Sleep(10); }
    while(GetTickCount64()<end);
    std::fprintf(stderr,"runtime status timeout\n%s\n",Read(dir).c_str()); assert(false); return {};
}
static std::string Permit(uint64_t epoch,uint64_t request,uint64_t frame,uint32_t dt=200000) {
    return "protocol=1\nepoch="+std::to_string(epoch)+"\nrequest="+std::to_string(request)+
        "\naction=permit\nframe="+std::to_string(frame)+"\ndt_us="+std::to_string(dt)+"\n";
}
static std::wstring NewDirectory(unsigned test) {
    wchar_t temp[MAX_PATH]{}; assert(GetTempPathW(MAX_PATH,temp));
    auto dir=std::wstring(temp)+L"TF2_probe_runtime_\u00e4_\u65e5_"+
        std::to_wstring(GetCurrentProcessId())+L"_"+std::to_wstring(test);
    assert(CreateDirectoryW(dir.c_str(),nullptr)); return dir;
}
static void Cleanup(const std::wstring& dir) {
    // Only the known files created by this test; no recursive filesystem action.
    for(auto leaf:{L"native_control.txt",L"native_status.txt",L"native_status.txt.tmp",L"producer.tmp"})
        DeleteFileW((dir+L"\\"+leaf).c_str());
    assert(RemoveDirectoryW(dir.c_str()));
}
static void Begin(World& w,const std::wstring& dir,uint64_t epoch) {
    w=World{}; TF2StepProbe_RuntimeTestReset(); TF2StepProbe_TestReset(Step,Speed,Clock);
    assert(TF2StepProbe_RuntimeStart(dir.c_str(),epoch,TF2_PROBE_STARTUP_QUIESCENT)==TF2_PROBE_OK);
    const auto status=Wait(dir,[](const auto& s){return Field(s,"ready")==1;});
    assert(Field(status,"abi")==3 && Field(status,"native_step_us")==200000);
}

int main() {
    World w;
    assert(TF2StepProbe_RuntimeStart(L"relative",1,TF2_PROBE_STARTUP_QUIESCENT)==TF2_RUNTIME_BAD_DIRECTORY);
    auto dir=NewDirectory(1); Begin(w,dir,41);
    assert(TF2StepProbe_RuntimeStart(dir.c_str(),41,TF2_PROBE_STARTUP_QUIESCENT)==TF2_PROBE_DUPLICATE);
    Write(dir,""); Sleep(30);
    assert(Field(Read(dir),"request_received")==0);
    Write(dir,Permit(41,1,1));
    Wait(dir,[](const auto&s){return Field(s,"request_acknowledged")==1;});
    auto before=Read(dir); assert(Field(before,"request_completed")==0);
    TF2StepProbe_TestStep(&w,200000,0);
    auto done=Wait(dir,[](const auto&s){return Field(s,"request_completed")==1;});
    assert(w.time==200 && Field(done,"time_after_ms")==200 && Field(done,"completed_dt_us")==200000);
    Write(dir,Permit(41,1,1)); Sleep(30);
    TF2StepProbe_TestStep(&w,200000,0); assert(w.time==200);
    Write(dir,Permit(41,2,2,0));
    Wait(dir,[](const auto&s){return Field(s,"request_acknowledged")==2;});
    TF2StepProbe_TestStep(&w,200000,0);
    done=Wait(dir,[](const auto&s){return Field(s,"request_completed")==2;});
    assert(w.time==200 && Field(done,"completed_dt_us")==0);
    // Emergency halt must bypass even an unread or missing permit request.
    Write(dir,"protocol=1\nepoch=41\nrequest=999\naction=halt\n");
    done=Wait(dir,[](const auto&s){return Field(s,"request_completed")==999;});
    assert(Field(done,"halted")==1 && Field(done,"ready")==0);
    TF2StepProbe_TestStep(&w,200000,0); assert(w.time==200);
    assert(!TF2StepProbe_RuntimeStop(41)); Cleanup(dir);

    // Same request number with different payload is terminal, never replayed.
    dir=NewDirectory(2); Begin(w,dir,42);
    Write(dir,Permit(42,1,1)); Wait(dir,[](const auto&s){return Field(s,"request_acknowledged")==1;});
    Write(dir,Permit(42,1,1,0));
    done=Wait(dir,[](const auto&s){return Field(s,"runtime_fault")==TF2_RUNTIME_REQUEST_CONFLICT;});
    assert(Field(done,"halted")==1); TF2StepProbe_TestStep(&w,200000,0); assert(w.time==0);
    assert(!TF2StepProbe_RuntimeStop(42)); Cleanup(dir);

    // Future request cannot skip the first command. A valid HALT still works.
    dir=NewDirectory(3); Begin(w,dir,43);
    Write(dir,Permit(43,2,1));
    Wait(dir,[](const auto&s){return Field(s,"runtime_fault")==TF2_RUNTIME_REQUEST_ORDER;});
    Write(dir,"protocol=1\nepoch=43\nrequest=3\naction=halt\nframe=0\ndt_us=0\n");
    Wait(dir,[](const auto&s){return Field(s,"request_completed")==3 && Field(s,"halted")==1;});
    assert(!TF2StepProbe_RuntimeStop(43)); Cleanup(dir);

    // Incomplete/oversized or duplicate-key records can never acknowledge work.
    for(unsigned i=4;i<=6;++i) {
        dir=NewDirectory(i); Begin(w,dir,40+i);
        std::string bad=i==4 ? Permit(44,1,1)+"frame=1\n" : i==5 ? std::string(4097,'x') : Permit(46,1,1);
        if(i==6) bad.pop_back();
        Write(dir,bad);
        done=Wait(dir,[](const auto&s){return Field(s,"runtime_fault")==TF2_RUNTIME_BAD_RECORD;});
        assert(Field(done,"halted")==1 && Field(done,"request_completed")==0);
        assert(!TF2StepProbe_RuntimeStop(40+i)); Cleanup(dir);
    }
    // Deleting an already consumed mailbox is a terminal I/O fault.
    dir=NewDirectory(7); Begin(w,dir,47);
    Write(dir,Permit(47,1,1)); Wait(dir,[](const auto&s){return Field(s,"request_acknowledged")==1;});
    assert(DeleteFileW((dir+L"\\native_control.txt").c_str()));
    done=Wait(dir,[](const auto&s){return Field(s,"runtime_fault")==TF2_RUNTIME_IO_ERROR;});
    assert(Field(done,"halted")==1 && Field(done,"io_operation")==1);
    assert(Field(done,"win32_error")==ERROR_FILE_NOT_FOUND);
    assert(!TF2StepProbe_RuntimeStop(47)); Cleanup(dir);

    // A broken status destination must stop the gate too. Recovering the file
    // path permits diagnostics again, never a silent resume of simulation.
    dir=NewDirectory(8); Begin(w,dir,48);
    const auto blockedPath=dir+L"\\native_status.txt.tmp";
    assert(CreateDirectoryW(blockedPath.c_str(),nullptr));
    Write(dir,Permit(48,1,1));
    const auto deadline=GetTickCount64()+5000;
    TF2ProbeStatus gate{};
    do { TF2StepProbe_GetStatus(&gate,sizeof gate); if(gate.halted) break; Sleep(10); }
    while(GetTickCount64()<deadline);
    assert(gate.halted);
    assert(RemoveDirectoryW(blockedPath.c_str()));
    done=Wait(dir,[](const auto&s){return Field(s,"runtime_fault")==TF2_RUNTIME_IO_ERROR;});
    assert(Field(done,"halted")==1 && Field(done,"io_operation")==4);
    TF2StepProbe_TestStep(&w,200000,0); assert(w.time==0);
    assert(!TF2StepProbe_RuntimeStop(48)); Cleanup(dir);

    // ABI 2 / Alpha4's 100 ms advance record is rejected before a permit reaches
    // the simulation thread. A subsequent held traversal still gets valid dt.
    dir=NewDirectory(9); Begin(w,dir,49);
    Write(dir,Permit(49,1,1,100000));
    done=Wait(dir,[](const auto&s){return Field(s,"runtime_fault")==TF2_RUNTIME_BAD_RECORD;});
    assert(Field(done,"halted")==1 && Field(done,"request_acknowledged")==0 && Field(done,"request_completed")==0);
    TF2StepProbe_TestStep(&w,200000,0);
    assert(w.time==0);
    assert(!TF2StepProbe_RuntimeStop(49)); Cleanup(dir);

    // Reproduce a real Windows reader with no FILE_SHARE_DELETE, as used by
    // CRT/Lua io.open: its short read must delay publication, not end the test.
    dir=NewDirectory(10); Begin(w,dir,50);
    HANDLE reader=LockStatusAgainstReplacement(dir);
    Write(dir,Permit(50,1,1));
    const auto transientEnd=GetTickCount64()+1000;
    do { TF2StepProbe_GetStatus(&gate,sizeof gate); if(gate.pending_state) break; Sleep(1); }
    while(GetTickCount64()<transientEnd);
    assert(gate.pending_state && !gate.halted);
    WaitForContention(false);
    Sleep(75); // Several actual failed MoveFileExW attempts while this handle is open.
    TF2StepProbe_GetStatus(&gate,sizeof gate); assert(!gate.halted);
    assert(CloseHandle(reader));
    done=Wait(dir,[](const auto&s){return Field(s,"request_acknowledged")==1 && Field(s,"status_replace_retries")>0;});
    assert(Field(done,"runtime_fault")==0 && Field(done,"win32_error")==0);
    assert(Field(done,"status_last_retry_error")==ERROR_ACCESS_DENIED ||
           Field(done,"status_last_retry_error")==ERROR_SHARING_VIOLATION);
    TF2StepProbe_TestStep(&w,200000,0);
    done=Wait(dir,[](const auto&s){return Field(s,"request_completed")==1;});
    assert(w.time==200 && Field(done,"time_after_ms")==200);
    assert(!TF2StepProbe_RuntimeStop(50)); Cleanup(dir);

    // A reader which never releases the file remains a terminal error after
    // the bounded retry budget. Releasing it publishes diagnostics only.
    dir=NewDirectory(11); Begin(w,dir,51);
    reader=LockStatusAgainstReplacement(dir);
    const auto persistentBegin=GetTickCount64();
    Write(dir,Permit(51,1,1));
    do { TF2StepProbe_GetStatus(&gate,sizeof gate); if(gate.halted) break; Sleep(5); }
    while(GetTickCount64()-persistentBegin<1500);
    assert(gate.halted && GetTickCount64()-persistentBegin<1500);
    assert(CloseHandle(reader));
    done=Wait(dir,[](const auto&s){return Field(s,"runtime_fault")==TF2_RUNTIME_IO_ERROR;});
    assert(Field(done,"halted")==1 && Field(done,"status_replace_retries")>0 && Field(done,"io_operation")==7);
    TF2StepProbe_TestStep(&w,200000,0); assert(w.time==0);
    assert(!TF2StepProbe_RuntimeStop(51)); Cleanup(dir);

    // Real CRT reads race 200 permit/complete publications. Every successful
    // read must see one complete record; the publisher never truncates live data.
    dir=NewDirectory(12); Begin(w,dir,52);
    std::atomic<bool> reading{true}; std::atomic<unsigned> wholeReads{0};
    const auto statusPath=dir+L"\\native_status.txt";
    std::thread crtReader([&] {
        while(reading.load()) {
            FILE* input=nullptr;
            if(_wfopen_s(&input,statusPath.c_str(),L"rb")==0 && input) {
                char data[4097]{};
                const auto got=std::fread(data,1,sizeof(data),input);
                assert(!std::ferror(input));
                Sleep(1); // Keep the ordinary CRT reader open across publisher attempts.
                assert(std::fclose(input)==0);
                CheckWholeSnapshot(std::string(data,got));
                ++wholeReads;
            }
            Sleep(1);
        }
    });
    for(uint64_t i=1;i<=200;++i) {
        Write(dir,Permit(52,i,i));
        Wait(dir,[&](const auto&s){return Field(s,"request_acknowledged")==i;});
        TF2StepProbe_TestStep(&w,200000,0);
        done=Wait(dir,[&](const auto&s){return Field(s,"request_completed")==i;});
        assert(Field(done,"runtime_fault")==0 && Field(done,"halted")==0);
        assert(Field(done,"time_after_ms")==i*200);
    }
    reading=false; crtReader.join();
    assert(wholeReads.load()>100 && w.time==40000);
    assert(!TF2StepProbe_RuntimeStop(52)); Cleanup(dir);

    // Opening control can also briefly meet a replacement/delete-pending
    // handle. Sharing contention waits; an actually deleted record still fails
    // immediately as checked in case 7, never becoming an empty mailbox.
    dir=NewDirectory(13); Begin(w,dir,53);
    Write(dir,Permit(53,1,1));
    Wait(dir,[](const auto&s){return Field(s,"request_acknowledged")==1;});
    TF2StepProbe_TestStep(&w,200000,0);
    Wait(dir,[](const auto&s){return Field(s,"request_completed")==1;});
    const auto controlPath=dir+L"\\native_control.txt";
    HANDLE exclusive=OpenTestReader(controlPath,0);
    WaitForContention(true);
    Sleep(75);
    TF2StepProbe_GetStatus(&gate,sizeof gate); assert(!gate.halted);
    assert(CloseHandle(exclusive));
    done=Wait(dir,[](const auto&s){return Field(s,"control_open_retries")>0;});
    assert(Field(done,"runtime_fault")==0 && Field(done,"io_operation")==0 && Field(done,"win32_error")==0);
    TF2StepProbe_TestStep(&w,200000,0); assert(w.time==200);
    assert(!TF2StepProbe_RuntimeStop(53)); Cleanup(dir);

    dir=NewDirectory(14); Begin(w,dir,54);
    Write(dir,Permit(54,1,1));
    Wait(dir,[](const auto&s){return Field(s,"request_acknowledged")==1;});
    const auto persistentControlPath=dir+L"\\native_control.txt";
    exclusive=OpenTestReader(persistentControlPath,0);
    const auto controlBegin=GetTickCount64();
    do { TF2StepProbe_GetStatus(&gate,sizeof gate); if(gate.halted) break; Sleep(5); }
    while(GetTickCount64()-controlBegin<1500);
    assert(gate.halted && GetTickCount64()-controlBegin<1500);
    assert(CloseHandle(exclusive));
    done=Wait(dir,[](const auto&s){return Field(s,"runtime_fault")==TF2_RUNTIME_IO_ERROR;});
    assert(Field(done,"halted")==1 && Field(done,"io_operation")==1 && Field(done,"control_open_retries")>0);
    assert(Field(done,"win32_error")==ERROR_SHARING_VIOLATION);
    TF2StepProbe_TestStep(&w,200000,0); assert(w.time==0);
    assert(!TF2StepProbe_RuntimeStop(54)); Cleanup(dir);
    std::puts("probe runtime ABI 3: 14 cases passed, including real Windows transient/persistent status replacement and control-open contention, original fault context, and 200 concurrent CRT-reader permit rounds with complete atomic snapshots");
}
