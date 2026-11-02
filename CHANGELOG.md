# Changelog

All notable changes to eclipse health are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to follow [Semantic Versioning](https://semver.org/).

## [0.1.0-alpha] — 2026-11-01

First public alpha. Windows 10/11 x64. **Pre-release**: the installer is unsigned and some vendor importers are experimental.

### Added

- **ECG import** — WFDB, CSV, EDF and SCP-ECG; Apple Health ECG CSV, Samsung and Huawei watch exports (experimental). Drag and drop, format auto-detection, import preview.
- **Health data import** — Apple Health exports (`export.xml`/zip) and Xiaomi activity CSV: steps, heart rate, sleep, weight and blood pressure.
- **Analysis** — built-in Cardia 2.0 ONNX engine: signal quality, R peaks, per-beat N / SVEB / VEB / F classification, heart-rate and interval measurements. Engine registry supports switching and re-analysis.
- **Records** — library with filters, favourites, record detail with waveform zoom and lead switching, soft delete.
- **Trends and comparison** — metric trends over time and side-by-side record comparison.
- **Reports** — local PDF / PNG report generation with redaction and a non-diagnostic watermark.
- **Overview and scores** — composite health score, rule-based suggestions, drag-and-drop layout editor with import/export.
- **AI assistant (optional)** — OpenAI, Anthropic, local Ollama or OpenAI-compatible endpoints; DPAPI-encrypted keys; visible tool calls; summaries and measurements only.
- **Coach and memory** — sleep / heart / exercise / stress / weight presets, Open-Meteo weather, editable personal memory.
- **Themes and motion** — 8 themes, eclipse launch animation, ripple logo, reduced-motion support.
- **Module system** — `.ehmod` install/uninstall, permissions and audit log, stdio JSON-RPC in isolated processes, per-module venvs; first-party modules ship preinstalled and removable.
- **Module marketplace** — official, community and local install sources; Ed25519-signed indexes; SHA-256 package checks; automated scanning.
- **32 official and community modules** — ECG/HRV, sleep/activity, nutrition/metabolism, psychology/habits, import/export, UI widgets, plus Relay ECG and Relay sleep model zoo modules.
- **External API** — local REST/OpenAPI, OpenAI-compatible endpoint and stdio MCP, with API keys managed in Settings.
- **Data management** — ZIP / JSON / CSV backup and restore, privacy clean-up, diagnostics export.

### Known limitations

- Alpha: unknown bugs are still being found; UI and behaviour can change.
- Some data cannot be read: vendor watch/health exports are experimental and can fail depending on device, OS and export method.
- Python and dependency versions affect some features when running from source, installing modules or re-exporting models.
- Modules are not fully tested; a successful install does not guarantee working functionality.
- Core ECG import + Cardia 2.0 beat analysis is the most stable path.
- Auto-update is not enabled.
- Windows only.
- One built-in analysis engine (Cardia 2.0); third-party engines install as modules.
- The installer is not code-signed.

### Release assets

The current installer name, size and SHA-256 are published on the [release page](https://github.com/Muhan-Qiu/eclipse-health/releases/tag/v0.1.0-alpha). Every release also carries a `SHA256SUMS.txt` asset; verify the downloaded file against it:

```powershell
Get-FileHash ".\<installer>.exe" -Algorithm SHA256
```
