// Standalone Windows integration checks. Never loads or starts the game.
#include "../upstream/tpf2-multiplayer/bridge/src/launch_lease.h"
#include "../upstream/tpf2-multiplayer/bridge/src/activation_pipe.h"
#include <cassert>
#include <iostream>
#include <thread>

static void Write(const std::wstring& path, const std::string& value) {
    HANDLE file = CreateFileW(path.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    assert(file != INVALID_HANDLE_VALUE);
    DWORD written = 0;
    assert(WriteFile(file, value.data(), DWORD(value.size()), &written, nullptr) && written == value.size());
    CloseHandle(file);
}

static PROCESS_INFORMATION Child(const std::wstring& exe, const std::wstring& args) {
    std::wstring cmd = L"\"" + exe + L"\" " + args;
    STARTUPINFOW si = {}; si.cb = sizeof(si);
    PROCESS_INFORMATION pi = {};
    assert(CreateProcessW(exe.c_str(), &cmd[0], nullptr, nullptr, FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi));
    CloseHandle(pi.hThread);
    return pi;
}

static DWORD Finish(PROCESS_INFORMATION pi) {
    DWORD wait = WaitForSingleObject(pi.hProcess, 5000);
    if (wait != WAIT_OBJECT_0) { TerminateProcess(pi.hProcess, 99); assert(false && "test helper timed out"); }
    DWORD code = 0; assert(GetExitCodeProcess(pi.hProcess, &code));
    CloseHandle(pi.hProcess); return code;
}

static bool PipeRead(const wchar_t* name, std::string& payload) {
    HANDLE pipe = CreateFileW(name, GENERIC_READ, 0, nullptr, OPEN_EXISTING, 0, nullptr);
    if (pipe == INVALID_HANDLE_VALUE) return false;
    char header[4]; DWORD read = 0;
    bool ok = ReadFile(pipe, header, 4, &read, nullptr) && read == 4;
    uint64_t length = 0;
    ok = ok && tf2coop::Decimal(std::string(header, ok ? 4 : 0), length) && length > 0 && length <= 4096;
    if (ok) {
        payload.resize(size_t(length));
        ok = ReadFile(pipe, &payload[0], DWORD(length), &read, nullptr) && read == length;
    }
    CloseHandle(pipe); return ok;
}

int wmain(int argc, wchar_t** argv) {
    if (argc == 2 && std::wstring(argv[1]) == L"--lease-child") {
        wchar_t env[8];
        if (GetEnvironmentVariableW(L"TF2COOP_SESSION", env, 8)) return 2;
        tf2coop::LaunchLease lease;
        return tf2coop::ReadValidLaunchLease(lease) ? 0 : 3;
    }
    if (argc == 3 && std::wstring(argv[1]) == L"--pipe-child") {
        std::string payload;
        return PipeRead(argv[2], payload) ? 4 : 0;
    }
    if (argc == 2 && std::wstring(argv[1]) == L"--exit-child") return 0;

    std::wstring exe;
    assert(tf2coop::CurrentExe(exe));
    wchar_t temp[MAX_PATH], unique[MAX_PATH];
    assert(GetTempPathW(MAX_PATH, temp));
    assert(GetTempFileNameW(temp, L"cpl", 0, unique));
    assert(DeleteFileW(unique)); assert(CreateDirectoryW(unique, nullptr));
    std::wstring state = std::wstring(unique) + L"\\TF2Coop";
    std::wstring data = std::wstring(unique) + L"\\session";
    assert(CreateDirectoryW(state.c_str(), nullptr)); assert(CreateDirectoryW(data.c_str(), nullptr));
    const wchar_t* config[] = {L"tpf2_bridge_mp.cfg", L"tpf2_slice.cfg", L"tpf2_instance.txt"};
    for (auto name : config) Write(data + L"\\" + name, "a\n");
    FILETIME created, exited, kernel, user;
    assert(GetProcessTimes(GetCurrentProcess(), &created, &exited, &kernel, &user));
    uint64_t now = tf2coop::UnixNow();
    std::string contents = "format=1\nlauncher_pid=" + std::to_string(GetCurrentProcessId())
        + "\nlauncher_created=" + std::to_string(tf2coop::FileTimeValue(created))
        + "\nexpires=" + std::to_string(now + 120)
        + "\ngame_exe=" + tf2coop::ToUtf8(exe) + "\ndata_dir=" + tf2coop::ToUtf8(data)
        + "\nnonce=0123456789abcdef0123456789abcdef\n";
    tf2coop::LaunchLease lease, bad;
    assert(tf2coop::ParseLaunchLease(contents, lease));
    assert(tf2coop::ValidateLaunchLease(lease, exe, now));
    bad = lease; bad.expires = now - 1; assert(!tf2coop::ValidateLaunchLease(bad, exe, now));
    bad = lease; bad.expires = now + 181; assert(!tf2coop::ValidateLaunchLease(bad, exe, now));
    bad = lease; ++bad.launcherCreated; assert(!tf2coop::ValidateLaunchLease(bad, exe, now));
    bad = lease; bad.launcherPid = 0; assert(!tf2coop::ValidateLaunchLease(bad, exe, now));
    assert(!tf2coop::ValidateLaunchLease(lease, exe + L".other", now));
    assert(DeleteFileW((data + L"\\tpf2_slice.cfg").c_str()));
    assert(!tf2coop::ValidateLaunchLease(lease, exe, now));
    Write(data + L"\\tpf2_slice.cfg", "a\n");
    assert(!tf2coop::ParseLaunchLease(contents + "format=1\n", bad));
    assert(!tf2coop::ParseLaunchLease(contents + "extra=value\n", bad));
    assert(!tf2coop::ParseLaunchLease(contents + std::string(1, '\0'), bad));
    assert(!tf2coop::ParseLaunchLease(std::string(4097, 'x'), bad));
    std::string relative = contents;
    auto offset = relative.find("data_dir=");
    relative.replace(offset, relative.find('\n', offset) - offset, "data_dir=C:relative");
    assert(!tf2coop::ParseLaunchLease(relative, bad));
    std::string invalidUtf8 = contents;
    invalidUtf8.insert(invalidUtf8.find("data_dir=") + 9, 1, char(0xff));
    assert(!tf2coop::ParseLaunchLease(invalidUtf8, bad));
    uint64_t number;
    assert(!tf2coop::Decimal("18446744073709551616", number));
    assert(!tf2coop::Decimal("-1", number));

    // A real new process inherits none of the opt-in session environment, but
    // can prove its live launcher's creation time and exact executable path.
    assert(SetEnvironmentVariableW(L"LOCALAPPDATA", unique));
    assert(SetEnvironmentVariableW(L"TF2COOP_SESSION", nullptr));
    Write(state + L"\\launch.cfg", contents);
    assert(Finish(Child(exe, L"--lease-child")) == 0);
    auto dead = Child(exe, L"--exit-child");
    assert(WaitForSingleObject(dead.hProcess, 5000) == WAIT_OBJECT_0);
    assert(GetProcessTimes(dead.hProcess, &created, &exited, &kernel, &user));
    bad = lease; bad.launcherPid = dead.dwProcessId; bad.launcherCreated = tf2coop::FileTimeValue(created);
    assert(!tf2coop::ValidateLaunchLease(bad, exe, now));
    CloseHandle(dead.hProcess);

    const std::wstring pipeName = L"\\\\.\\pipe\\TF2CoopActivation-test-" + std::to_wstring(GetCurrentProcessId());
    const std::string payload = "format=1\nactive=1\ndata_dir=C:/session\n";
    auto serveOne = [&](HANDLE pipe) {
        bool connected = ConnectNamedPipe(pipe, nullptr) || GetLastError() == ERROR_PIPE_CONNECTED;
        assert(connected);
        tf2coop::SendActivation(pipe, GetCurrentProcessId(), payload);
        DisconnectNamedPipe(pipe); CloseHandle(pipe);
    };
    HANDLE pipe = tf2coop::NewActivationPipe(pipeName.c_str(), true);
    assert(pipe != INVALID_HANDLE_VALUE);
    std::thread server(serveOne, pipe);
    std::string received;
    assert(PipeRead(pipeName.c_str(), received) && received == payload);
    server.join();
    pipe = tf2coop::NewActivationPipe(pipeName.c_str(), true);
    assert(pipe != INVALID_HANDLE_VALUE);
    std::thread rejectServer(serveOne, pipe);
    assert(Finish(Child(exe, L"--pipe-child \"" + pipeName + L"\"")) == 0);
    rejectServer.join();

    for (auto name : config) assert(DeleteFileW((data + L"\\" + name).c_str()));
    assert(DeleteFileW((state + L"\\launch.cfg").c_str()));
    assert(RemoveDirectoryW(data.c_str())); assert(RemoveDirectoryW(state.c_str())); assert(RemoveDirectoryW(unique));
    std::cout << "launch lease and process-bound activation checks passed (real helper processes)\n";
    return 0;
}
