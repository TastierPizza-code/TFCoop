// Launcher-owned, short-lived permission for a Steam-restarted game process.
// This contains data only. No DLL paths or executable configuration are read.
#pragma once
#include <windows.h>
#include <cstdint>
#include <cstdio>
#include <map>
#include <string>

namespace tf2coop {
struct LaunchLease {
    DWORD launcherPid = 0;
    uint64_t launcherCreated = 0;
    uint64_t expires = 0;
    std::wstring gameExe;
    std::wstring dataDir;
    std::string nonce;
};

inline uint64_t FileTimeValue(const FILETIME& value) {
    return (uint64_t(value.dwHighDateTime) << 32) | value.dwLowDateTime;
}
inline uint64_t UnixNow() {
    FILETIME value; GetSystemTimeAsFileTime(&value);
    return (FileTimeValue(value) - 116444736000000000ULL) / 10000000ULL;
}
inline bool Decimal(const std::string& text, uint64_t& out) {
    if (text.empty()) return false;
    uint64_t value = 0;
    for (char ch : text) {
        if (ch < '0' || ch > '9') return false;
        unsigned digit = ch - '0';
        if (value > (UINT64_MAX - digit) / 10) return false;
        value = value * 10 + digit;
    }
    out = value; return true;
}
inline bool Utf8(const std::string& text, std::wstring& out) {
    if (text.empty() || text.find('\0') != std::string::npos) return false;
    int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), int(text.size()), nullptr, 0);
    if (n <= 0) return false;
    out.resize(n);
    return MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, text.data(), int(text.size()), &out[0], n) == n;
}
inline bool AbsolutePath(const std::wstring& path) {
    if (path.size() < 3 || path.size() >= MAX_PATH - 40) return false;
    // Drive-absolute and UNC paths are supported; drive-relative/root-relative
    // paths depend on inherited working-directory state and are rejected.
    bool drive = ((path[0] >= L'A' && path[0] <= L'Z') || (path[0] >= L'a' && path[0] <= L'z'))
        && path[1] == L':' && (path[2] == L'\\' || path[2] == L'/');
    bool unc = path[0] == L'\\' && path[1] == L'\\' && path[2] != L'?' && path[2] != L'.';
    return drive || unc;
}
inline bool CanonicalPath(const std::wstring& path, std::wstring& result) {
    if (!AbsolutePath(path)) return false;
    wchar_t resolved[MAX_PATH];
    DWORD n = GetFullPathNameW(path.c_str(), MAX_PATH, resolved, nullptr);
    if (!n || n >= MAX_PATH) return false;
    result.assign(resolved, n);
    while (result.size() > 3 && result.back() == L'\\') result.pop_back();
    return true;
}
inline bool ParseLaunchLease(const std::string& text, LaunchLease& out) {
    if (text.empty() || text.size() > 4096 || text.find('\0') != std::string::npos) return false;
    std::map<std::string, std::string> fields;
    size_t pos = 0;
    while (pos < text.size()) {
        size_t end = text.find('\n', pos);
        if (end == std::string::npos) end = text.size();
        std::string line = text.substr(pos, end - pos);
        if (!line.empty() && line.back() == '\r') line.pop_back();
        size_t equal = line.find('=');
        if (equal == std::string::npos || equal == 0 || line.find('\r') != std::string::npos) return false;
        if (!fields.emplace(line.substr(0, equal), line.substr(equal + 1)).second) return false;
        pos = end + 1;
    }
    const char* expected[] = {"format", "launcher_pid", "launcher_created", "expires", "game_exe", "data_dir", "nonce"};
    if (fields.size() != 7) return false;
    for (auto key : expected) if (!fields.count(key)) return false;
    if (fields["format"] != "1") return false;
    LaunchLease parsed;
    uint64_t pid = 0;
    if (!Decimal(fields["launcher_pid"], pid) || !pid || pid > MAXDWORD
        || !Decimal(fields["launcher_created"], parsed.launcherCreated) || !parsed.launcherCreated
        || !Decimal(fields["expires"], parsed.expires)) return false;
    parsed.launcherPid = DWORD(pid);
    std::wstring game, data;
    if (!Utf8(fields["game_exe"], game) || !CanonicalPath(game, parsed.gameExe)
        || !Utf8(fields["data_dir"], data) || !CanonicalPath(data, parsed.dataDir)) return false;
    parsed.nonce = fields["nonce"];
    if (parsed.nonce.size() != 32) return false;
    for (char c : parsed.nonce) if (!(c >= '0' && c <= '9') && !(c >= 'a' && c <= 'f')) return false;
    out = parsed; return true;
}
inline bool ReadSmallFile(const std::wstring& path, std::string& data) {
    // Launcher writes through atomic replacement, so either complete generation
    // is visible. File sharing also allows revocation while the game reads it.
    HANDLE file = CreateFileW(path.c_str(), GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    LARGE_INTEGER size;
    bool ok = GetFileSizeEx(file, &size) && size.QuadPart > 0 && size.QuadPart <= 4096;
    if (ok) {
        data.resize(size_t(size.QuadPart));
        DWORD read = 0;
        ok = ReadFile(file, &data[0], DWORD(data.size()), &read, nullptr) && read == data.size();
    }
    CloseHandle(file); return ok;
}
inline bool StatePath(const wchar_t* name, std::wstring& path) {
    wchar_t local[MAX_PATH];
    DWORD n = GetEnvironmentVariableW(L"LOCALAPPDATA", local, MAX_PATH);
    if (!n || n >= MAX_PATH) return false;
    path = std::wstring(local) + L"\\TF2Coop\\" + name;
    return path.size() < MAX_PATH;
}
inline bool CurrentExe(std::wstring& out) {
    wchar_t exe[MAX_PATH];
    DWORD n = GetModuleFileNameW(nullptr, exe, MAX_PATH);
    return n && n < MAX_PATH && CanonicalPath(std::wstring(exe, n), out);
}
inline bool IsFile(const std::wstring& path) {
    DWORD attr = GetFileAttributesW(path.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY);
}
inline bool ValidateLaunchLease(const LaunchLease& lease, const std::wstring& actualExe, uint64_t now) {
    if (lease.expires < now || lease.expires - now > 180 || _wcsicmp(lease.gameExe.c_str(), actualExe.c_str()) != 0) return false;
    HANDLE launcher = OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, FALSE, lease.launcherPid);
    if (!launcher) return false;
    FILETIME created, exited, kernel, user;
    bool live = WaitForSingleObject(launcher, 0) == WAIT_TIMEOUT
        && GetProcessTimes(launcher, &created, &exited, &kernel, &user)
        && FileTimeValue(created) == lease.launcherCreated;
    CloseHandle(launcher);
    if (!live) return false;
    DWORD attr = GetFileAttributesW(lease.dataDir.c_str());
    if (attr == INVALID_FILE_ATTRIBUTES || !(attr & FILE_ATTRIBUTE_DIRECTORY)) return false;
    for (auto name : {L"tpf2_bridge_mp.cfg", L"tpf2_slice.cfg", L"tpf2_instance.txt"})
        if (!IsFile(lease.dataDir + L"\\" + name)) return false;
    return true;
}
inline bool ReadValidLaunchLease(LaunchLease& lease) {
    std::wstring path, actual;
    std::string data;
    return StatePath(L"launch.cfg", path) && CurrentExe(actual) && ReadSmallFile(path, data)
        && ParseLaunchLease(data, lease) && ValidateLaunchLease(lease, actual, UnixNow());
}
} // namespace tf2coop
