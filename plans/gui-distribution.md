# GUI App Distribution Plan

How to distribute KohakuTerrarium's web-based GUI (FastAPI + Vue 3) as a desktop application.

## Research Summary

### Webview Wrappers (web app in native window)

| Option | Binary Size | Startup | Engine | Notes |
|--------|-------------|---------|--------|-------|
| **pywebview** (v6.1) | Tiny (uses OS webview) | 1-2s | Native (WebKit/Edge/GTK) | Simplest. v6 adds shared state, network hooks. Known issue: FastAPI and pywebview both want the main thread. Run uvicorn in background thread. |
| **Tauri** (v2.10) | 2.5-10 MB | <0.5s | OS native webview | Best desktop experience. Python via sidecar (PyInstaller binary). Template exists: `vue-tauri-fastapi-sidecar-template`. Supports system tray, notifications, auto-update, multi-window. |
| **PyTauri** (v0.8) | 10-20 MB | <1s | OS native webview | Native Python binding via Pyo3. No IPC overhead. Async Python support. Pre-1.0 but most promising future path. |
| **Electron** | 150-250 MB | 0.5-2s | Bundled Chromium | Proven but heavy. Only justified if you need full Chromium APIs. |
| **Pyloid** (v0.27) | 50-100 MB | 1-2s | QtWebEngine | PySide6-based. Consistent rendering but bundles Qt engine. LGPL concern. |

### Python Freezers (standalone executables)

| Option | Binary Size | Startup | Quality | Notes |
|--------|-------------|---------|---------|-------|
| **Nuitka** (v2.8) | 20-60 MB | Fast | Compiled C | Best performance. FastAPI works in single-worker mode. 2-4x faster than CPython. |
| **PyInstaller** (v6.19) | 25-95 MB | 2-50s | Bundled | Most common. asyncio issues on Windows. Slow onefile startup. |
| **cx_Freeze** (v8.6) | 25-80 MB | 1.8s | Bundled | Better startup than PyInstaller. No onefile mode. |
| **PyApp** | ~5 MB wrapper | First-run delay | Runtime install | Downloads Python on first run. Simplest to create. |
| **Shiv** | 10-30 MB | Fast | Zipapp | Requires system Python. Good for servers. |

### Alternative Frontends (Python-native)

| Option | Replaces Vue? | Desktop mode? | Notes |
|--------|--------------|---------------|-------|
| **NiceGUI** (v3.0) | Partially | Yes (pywebview) | Built on FastAPI. Pure Python UI. Won't match our Vue frontend in flexibility. |
| **Gradio** | No | No | ML demos only. Too limited. |
| **Streamlit** | No | Community only | Re-renders everything. Not suitable. |
| **textual-web** | No (TUI only) | N/A | Could serve our existing Textual TUI in browser. Interesting complement. |

### Distribution Channels

| Channel | Platform | Requires | Notes |
|---------|----------|----------|-------|
| **pipx** | Any with Python | Python | `pipx install kohakuterrarium`. Best for developers. |
| **Homebrew** | macOS/Linux | Formula | `brew install kohakuterrarium`. FastAPI already has a formula. |
| **winget** | Windows | MSI/EXE installer | `winget install kohakuterrarium`. Needs proper installer. |
| **Snap** | Ubuntu | snapcraft.yaml | Auto-updates. Ubuntu-focused. |
| **Flatpak** | Linux | Flathub | Community-backed. Best for Linux desktop. |
| **AppImage** | Linux | AppImage tools | Single file, no install. Portable. |
| **Docker** | Any with Docker | Dockerfile | Standard for server deployment. |

## Recommended Roadmap

### Phase 1: `kt web` command (do now)

Serve the built Vue frontend as static files from FastAPI. Single command, single port.

```bash
kt web                    # starts on localhost:8001
kt web --port 3000        # custom port
kt web --host 0.0.0.0     # expose to network
```

Implementation:
1. `npm run build` outputs to `src/kohakuterrarium/web_dist/`
2. FastAPI mounts: `app.mount("/", StaticFiles(directory=web_dist, html=True))`
3. Build in CI, include in wheel via `package-data`

### Phase 2: pywebview desktop window (soon)

```bash
pip install kohakuterrarium[gui]
kt web                    # opens native window (or browser if pywebview unavailable)
```

Implementation:
- Optional pywebview dependency in `[gui]` extra
- Run uvicorn in background thread, pywebview in main thread
- Fallback to `webbrowser.open()` if pywebview not installed

### Phase 3: Standalone executable (later)

For non-Python users. Use PyApp or Nuitka.

- PyApp: single-file wrapper, downloads Python on first run. Simplest to create.
- Nuitka: compiled binary, better performance. Needs C compiler on build machine.
- CI/CD builds for Linux/macOS/Windows

### Phase 4: Tauri desktop app (if needed)

Only if native features are needed (system tray, notifications, auto-update).

- Use `vue-tauri-fastapi-sidecar-template` as starting point
- Sidecar: Nuitka-compiled FastAPI server
- Tauri shell: 10 MB, native window + system integration
- Watch PyTauri for deeper integration without sidecar

## Build Pipeline

```
CI/CD:
  1. npm run build  (apps/web/ -> src/kohakuterrarium/web_dist/)
  2. python -m build (creates wheel with web_dist included)
  3. Optional: Nuitka compile for standalone
  4. Optional: Tauri build for desktop
```

## textual-web as Bonus

Our TUI already runs on Textual. With `textual-serve`, we could serve it in a browser with 3 lines of code. This gives a lightweight browser-based TUI option alongside the full Vue web UI. Worth offering as `kt tui-web` for SSH/remote scenarios.
