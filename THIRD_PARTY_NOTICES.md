# Third-party notices

The native multiplayer implementation is derived from silver2127/tpf2-multiplayer.
Pinned upstream commit: `7e8e49ead4966dda9b885d1a484c67b0ad648ee4`.
Source: https://github.com/silver2127/tpf2-multiplayer

Its MIT license is retained in `upstream/tpf2-multiplayer/LICENSE`.
Additional upstream notices are retained in `upstream/tpf2-multiplayer/THIRD_PARTY_NOTICES.md`.
Local changes include opt-in process launch, configuration lookup, transport validation,
sequence/ACK hardening, a disabled automatic save-file server, and more precise diagnostics.
See `docs/UPSTREAM.patch` in the source project/package for the exact changes.

The portable launcher bundles CPython and Tcl/Tk, their license files are retained by
the PyInstaller distribution and additionally collected under `licenses/` when available.
PyInstaller uses GPL with its distribution exception; the launcher is not required to be GPL.
PyInstaller, pyinstaller-hooks-contrib and their bundled licenses are copied to `licenses/`.

No original Transport Fever 2 executable, audio library, game assets, savegame or Steamworks
SDK is redistributed. `alut.dll` in native/out is a newly built forwarding proxy; the user's
original file is backed up locally during installation.
