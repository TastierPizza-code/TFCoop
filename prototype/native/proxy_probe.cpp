// Isolated diagnostic audio proxy. Does not load the Alpha bridge or capture DLL.
// A live, short-lived prototype controller lease is required on every game start.
#include <windows.h>
#include <cstdio>
#include <string>
#include "../../upstream/tpf2-multiplayer/bridge/src/launch_lease.h"

#pragma comment(linker, "/export:alutCreateBufferFromFile=alut_real.alutCreateBufferFromFile")
#pragma comment(linker, "/export:alutCreateBufferFromFileImage=alut_real.alutCreateBufferFromFileImage")
#pragma comment(linker, "/export:alutCreateBufferHelloWorld=alut_real.alutCreateBufferHelloWorld")
#pragma comment(linker, "/export:alutCreateBufferWaveform=alut_real.alutCreateBufferWaveform")
#pragma comment(linker, "/export:alutExit=alut_real.alutExit")
#pragma comment(linker, "/export:alutGetError=alut_real.alutGetError")
#pragma comment(linker, "/export:alutGetErrorString=alut_real.alutGetErrorString")
#pragma comment(linker, "/export:alutGetMIMETypes=alut_real.alutGetMIMETypes")
#pragma comment(linker, "/export:alutGetMajorVersion=alut_real.alutGetMajorVersion")
#pragma comment(linker, "/export:alutGetMinorVersion=alut_real.alutGetMinorVersion")
#pragma comment(linker, "/export:alutInit=alut_real.alutInit")
#pragma comment(linker, "/export:alutInitWithoutContext=alut_real.alutInitWithoutContext")
#pragma comment(linker, "/export:alutLoadMemoryFromFile=alut_real.alutLoadMemoryFromFile")
#pragma comment(linker, "/export:alutLoadMemoryFromFileImage=alut_real.alutLoadMemoryFromFileImage")
#pragma comment(linker, "/export:alutLoadMemoryHelloWorld=alut_real.alutLoadMemoryHelloWorld")
#pragma comment(linker, "/export:alutLoadMemoryWaveform=alut_real.alutLoadMemoryWaveform")
#pragma comment(linker, "/export:alutLoadWAVFile=alut_real.alutLoadWAVFile")
#pragma comment(linker, "/export:alutLoadWAVMemory=alut_real.alutLoadWAVMemory")
#pragma comment(linker, "/export:alutSleep=alut_real.alutSleep")
#pragma comment(linker, "/export:alutUnloadWAV=alut_real.alutUnloadWAV")

namespace {
HMODULE selfModule = nullptr;
bool ReadLease(tf2coop::LaunchLease& lease) {
    wchar_t local[MAX_PATH] = {};
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH);
    if (!n || n >= MAX_PATH) return false;
    std::string text;
    std::wstring actual;
    if (!tf2coop::ReadSmallFile(std::wstring(local) + L"\\TF2StrictProbe\\launch.cfg", text)
        || !tf2coop::ParseLaunchLease(text, lease) || !tf2coop::CurrentExe(actual)) return false;
    const auto now = tf2coop::UnixNow();
    if (lease.expires < now || lease.expires - now > 120
        || _wcsicmp(lease.gameExe.c_str(), actual.c_str())) return false;
    HANDLE owner = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, lease.launcherPid);
    if (!owner) return false;
    FILETIME created, exited, kernel, user;
    bool valid = WaitForSingleObject(owner, 0) == WAIT_TIMEOUT
        && GetProcessTimes(owner, &created, &exited, &kernel, &user)
        && tf2coop::FileTimeValue(created) == lease.launcherCreated;
    CloseHandle(owner);
    DWORD attr = GetFileAttributesW(lease.dataDir.c_str());
    return valid && attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY);
}

void Report(const std::wstring& directory, unsigned result) {
    const auto path = directory + L"\\loader_status.txt";
    FILE* file = nullptr;
    if (!_wfopen_s(&file, path.c_str(), L"wb") && file) {
        std::fprintf(file, "protocol=1\npid=%lu\nresult=%u\n", GetCurrentProcessId(), result);
        std::fclose(file);
    }
}

DWORD WINAPI StartProbe(void*) {
    tf2coop::LaunchLease lease;
    if (!ReadLease(lease)) return 0;
    std::string number;
    uint64_t epoch = 0;
    if (!tf2coop::ReadSmallFile(lease.dataDir + L"\\probe_epoch.txt", number)) {
        Report(lease.dataDir, 1001); return 0;
    }
    while (!number.empty() && (number.back() == '\n' || number.back() == '\r')) number.pop_back();
    if (!tf2coop::Decimal(number, epoch) || !epoch || epoch > 9007199254740991ull) {
        Report(lease.dataDir, 1002); return 0;
    }
    wchar_t path[MAX_PATH] = {};
    DWORD length = GetModuleFileNameW(selfModule, path, MAX_PATH);
    wchar_t* slash = wcsrchr(path, L'\\');
    if (!length || length >= MAX_PATH || !slash) { Report(lease.dataDir, 1003); return 0; }
    slash[1] = 0;
    if (wcscat_s(path, L"tf2_step_probe.dll")) { Report(lease.dataDir, 1003); return 0; }
    HMODULE probe = LoadLibraryExW(path, nullptr, LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR | LOAD_LIBRARY_SEARCH_SYSTEM32);
    if (!probe) { Report(lease.dataDir, 1004); return 0; }
    using Start = uint32_t(*)(const wchar_t*, uint64_t, uint32_t);
    auto start = reinterpret_cast<Start>(GetProcAddress(probe, "TF2StepProbe_RuntimeStart"));
    if (!start) { Report(lease.dataDir, 1005); FreeLibrary(probe); return 0; }
    // Dedicated prototype launch only; this runs during startup before a save
    // is selected. Runtime refuses incompatible or already patched Step code.
    uint32_t result = start(lease.dataDir.c_str(), epoch, 0x51554945);
    Report(lease.dataDir, result);
    // Successful hooks pin their DLL. Keep failed partial initialization resident
    // too; its own status explains the failure and no UI success is fabricated.
    return 0;
}
} // namespace

BOOL WINAPI DllMain(HINSTANCE module, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) {
        selfModule = module;
        DisableThreadLibraryCalls(module);
        HANDLE thread = CreateThread(nullptr, 0, StartProbe, nullptr, 0, nullptr);
        if (thread) CloseHandle(thread);
    }
    return TRUE;
}
