// Proxy alut.dll -- the earliest reliable foothold in the process.
//
// Why: the title-screen menu (UI::CMenuUI::CreatePageMain) is built long before
// a save is loaded, so injecting into a running game is far too late to touch
// it. alut.dll is a *static* import of TransportFever2.exe, so the loader maps
// it before the exe's entry point runs. Dropping ourselves in its place gets us
// running early enough to install the hooks before a save is loaded. Ordinary
// Steam launches forward audio only; the companion opts in a co-op session.
//
// Install: rename the stock alut.dll to alut_real.dll and put this beside it.
// Every export is forwarded straight through, so the game's audio is untouched.
//
// The native libraries are resolved only beside this proxy in the installation.
#include <windows.h>
#include <cstdio>
#include "launch_lease.h"
#include "activation_pipe.h"

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

// Resolve a shipped file beside THIS proxy DLL in the installation.
#include "datadir.h"

static void resolveShipped(const wchar_t* name, wchar_t* out, size_t cch)
{
    wchar_t buf[MAX_PATH];
    HMODULE self = nullptr;
    GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                       (LPCWSTR)&resolveShipped, &self);
    if (self && GetModuleFileNameW(self, buf, MAX_PATH)) {
        wchar_t* s = wcsrchr(buf, L'\\');
        if (s) { s[1] = 0; wcscat_s(buf, MAX_PATH, name);
                 if (GetFileAttributesW(buf) != INVALID_FILE_ATTRIBUTES) { wcscpy_s(out, cch, buf); return; } }
    }
    // No user profile/workshop fallback may substitute an unrelated DLL.
    out[0] = 0;
}

static void Log(const char* fmt, ...)
{
    // The log lives in the runtime data dir (%LOCALAPPDATA%\tpf2mp\data), like
    // every other log. Resolving it through resolveShipped sent it to the dev
    // workshop path on a fresh machine (no such dir -> log silently dropped).
    wchar_t path[MAX_PATH];
    if (!Tpf2mpDataDirW(path, MAX_PATH, (const void*)&resolveShipped)) return;
    wcscat_s(path, MAX_PATH, L"tpf2_proxy.log");
    FILE* f = nullptr;
    if (_wfopen_s(&f, path, L"ab") != 0 || !f) return;
    va_list ap; va_start(ap, fmt);
    vfprintf(f, fmt, ap);
    va_end(ap);
    fclose(f);
}

// Loading a dll from inside DllMain would deadlock on the loader lock, so the
// real work happens on its own thread during process startup.
static DWORD WINAPI LoadBridge(LPVOID)
{
    // Steam may replace the launcher child with a new process whose parent is
    // Steam itself. A live launcher can authorize that exact installation for
    // at most 180 seconds. This never changes the user's global environment.
    wchar_t session[8] = L"";
    bool childSession = GetEnvironmentVariableW(L"TF2COOP_SESSION", session, 8) == 1 && session[0] == L'1';
    tf2coop::LaunchLease lease;
    bool validLease = tf2coop::ReadValidLaunchLease(lease);
    if (!childSession && !validLease) return 0;
    if (validLease) {
        if (!SetEnvironmentVariableW(L"TPF2MP_DATADIR", lease.dataDir.c_str())
            || !SetEnvironmentVariableW(L"TF2COOP_SESSION", L"1")) return 0;
        Log("[coop] launcher lease accepted for pid=%lu\n", GetCurrentProcessId());
    } else {
        wchar_t data[MAX_PATH];
        DWORD n = GetEnvironmentVariableW(L"TPF2MP_DATADIR", data, MAX_PATH);
        if (!n || n >= MAX_PATH || !tf2coop::CanonicalPath(data, lease.dataDir)
            || !tf2coop::CurrentExe(lease.gameExe)) return 0;
        lease.nonce.assign(32, '0');
    }
    auto base = reinterpret_cast<const unsigned char*>(GetModuleHandleW(nullptr));
    auto dos = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
    if (!base || dos->e_magic != IMAGE_DOS_SIGNATURE) return 0;
    auto nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE || nt->FileHeader.TimeDateStamp != 0x675abcc6 ||
        nt->OptionalHeader.SizeOfImage != 0x046ce000) {
        Log("[coop] unsupported game build; native hooks disabled\n");
        return 0;
    }
    wchar_t bridgePath[MAX_PATH], menuPath[MAX_PATH], slicePath[MAX_PATH];
    resolveShipped(L"tpf2_bridge_mp.dll", bridgePath, MAX_PATH);
    resolveShipped(L"tpf2_menu.dll",      menuPath,   MAX_PATH);
    resolveShipped(L"tpf2_slice.dll",     slicePath,  MAX_PATH);
    HMODULE h = LoadLibraryW(bridgePath);
    Log("[proxy] pid=%lu bridge load %s (err %lu) from %ls\n",
        GetCurrentProcessId(), h ? "OK" : "FAILED", h ? 0 : GetLastError(), bridgePath);
    // The local companion owns the lobby. Do not load another menu/network app.
    // The slice dll (command capture/replay) is optional: a missing file just
    // means no replication this run, the menu + bridge still come up.
    HMODULE hs = LoadLibraryW(slicePath);
    Log("[proxy] pid=%lu slice load %s (err %lu) from %ls\n",
        GetCurrentProcessId(), hs ? "OK" : "FAILED", hs ? 0 : GetLastError(), slicePath);
    if (h && hs) {
        std::string payload = "format=1\nactive=1\ngame_pid=" + std::to_string(GetCurrentProcessId())
            + "\ngame_exe=" + tf2coop::ToUtf8(lease.gameExe) + "\ndata_dir=" + tf2coop::ToUtf8(lease.dataDir)
            + "\nnonce=" + lease.nonce + "\n";
        bool pipe = tf2coop::StartActivationPipes(payload);
        Log("[coop] process-bound Lua activation pipe %s pid=%lu\n", pipe ? "ready" : "FAILED", GetCurrentProcessId());
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinst);
        Log("[proxy] attached to pid %lu\n", GetCurrentProcessId());
        CreateThread(nullptr, 0, LoadBridge, nullptr, 0, nullptr);
    }
    return TRUE;
}
