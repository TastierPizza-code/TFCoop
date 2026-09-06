// Process-bound activation proof for the game's restricted Lua runtime.
// Lua's os.getenv can be absent or can retain a pre-Steam environment snapshot.
// An OS pipe cannot outlive its owner, and another game process is rejected.
#pragma once
#include <windows.h>
#include <cstdio>
#include <string>

namespace tf2coop {
static const wchar_t* const ActivationPipeName = L"\\\\.\\pipe\\TF2CoopActivation";

inline std::string ToUtf8(const std::wstring& value) {
    if (value.empty()) return std::string();
    int size = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), int(value.size()), nullptr, 0, nullptr, nullptr);
    if (size <= 0) return std::string();
    std::string result(size, '\0');
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, value.data(), int(value.size()), &result[0], size, nullptr, nullptr)) return std::string();
    return result;
}

inline bool SendActivation(HANDLE pipe, DWORD authorizedPid, const std::string& payload) {
    ULONG clientPid = 0;
    if (!GetNamedPipeClientProcessId(pipe, &clientPid) || clientPid != authorizedPid || payload.empty() || payload.size() > 4096) return false;
    char length[5];
    _snprintf_s(length, sizeof(length), _TRUNCATE, "%04u", unsigned(payload.size()));
    std::string frame(length, 4); frame += payload;
    DWORD written = 0;
    if (!WriteFile(pipe, frame.data(), DWORD(frame.size()), &written, nullptr) || written != frame.size()) return false;
    // Disconnect discards unread pipe bytes. The approved local Lua client
    // reads exactly the framed byte count then closes, so flushing finishes.
    return FlushFileBuffers(pipe) != FALSE;
}

struct ActivationWorker {
    HANDLE pipe;
    DWORD authorizedPid;
    std::string payload;
};
inline DWORD WINAPI ActivationWorkerMain(LPVOID value) {
    ActivationWorker* worker = static_cast<ActivationWorker*>(value);
    for (;;) {
        bool connected = ConnectNamedPipe(worker->pipe, nullptr) || GetLastError() == ERROR_PIPE_CONNECTED;
        if (connected) SendActivation(worker->pipe, worker->authorizedPid, worker->payload);
        else if (GetLastError() != ERROR_NO_DATA) break;
        DisconnectNamedPipe(worker->pipe);
    }
    CloseHandle(worker->pipe); delete worker; return 0;
}

inline HANDLE NewActivationPipe(const wchar_t* name, bool first) {
    return CreateNamedPipeW(name, PIPE_ACCESS_OUTBOUND | (first ? FILE_FLAG_FIRST_PIPE_INSTANCE : 0),
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
        8, 8192, 0, 50, nullptr);
}

inline bool StartActivationPipes(const std::string& payload) {
    if (payload.empty() || payload.size() > 4096) return false;
    HANDLE first = INVALID_HANDLE_VALUE;
    // Steam can launch the final process slightly before its bootstrap exits.
    // The old process's pipe disappears with it; no stale file can authorize us.
    for (unsigned attempt = 0; attempt < 1200; ++attempt) {
        first = NewActivationPipe(ActivationPipeName, true);
        if (first != INVALID_HANDLE_VALUE) break;
        DWORD error = GetLastError();
        if (error != ERROR_ACCESS_DENIED && error != ERROR_PIPE_BUSY) return false;
        Sleep(100);
    }
    if (first == INVALID_HANDLE_VALUE) return false;
    unsigned started = 0;
    for (unsigned i = 0; i < 8; ++i) {
        HANDLE pipe = i ? NewActivationPipe(ActivationPipeName, false) : first;
        if (pipe == INVALID_HANDLE_VALUE) continue;
        auto worker = new ActivationWorker{pipe, GetCurrentProcessId(), payload};
        HANDLE thread = CreateThread(nullptr, 0, ActivationWorkerMain, worker, 0, nullptr);
        if (thread) { CloseHandle(thread); ++started; }
        else { CloseHandle(pipe); delete worker; }
    }
    return started != 0;
}
} // namespace tf2coop
