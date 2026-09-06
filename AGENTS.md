# TFCoop maintenance

- The user works on this PC concurrently. Do not use computer control or start, stop, install into, or interact with TF2 during development. Use headless checks; installation and in-game tests are performed by the user through the launcher.
- Current public repository: https://github.com/TastierPizza-code/TFCoop. Keep current source and releases there when delivering a new version; the user has requested GitHub delivery and startup updates.
- Current launcher entry: probe_launcher.py; implementation: prototype/. Older coop/mod/upstream code is retained for comparison and shared helpers.
- Use prototype/release_version.py for the numeric release tag. Keep launcher display, mod name, guides and release notes consistent.
- Build a public TFCoop-Windows.zip with tools/build_probe_package.py and publish using tools/publish_release.py. Never publish --private-save builds, savegame pairs, session secrets, diagnostics, stock game files, local caches, or user-specific paths.
- Check downloaded release and file hashes before handoff. Do not update a running game/test, downgrade a cached release, or bypass validation on errors.
- Describe runtime evidence accurately. A headless model pass does not prove TF2 determinism, free concurrent construction, or native UI pause synchronization.
