# eclipse health module user guide

> For people using eclipse health. By the end you will know what modules do, where to install them, how to read permissions, and how to get your own AI agent to build one.
> Document version: 2026-11-01 · applies to 0.1.x.

## 1. What a module is

The eclipse health core keeps only data, permissions, lifecycle and audit. Everything else is a module:

- devices and data sources: Apple Health, Garmin, Fitbit, Withings, GPX tracks, Bluetooth devices;
- analysis models: HRV, ECG beat classification, sleep staging;
- UI components: dashboard cards, charts, activity heatmaps;
- exporters: WFDB, EDF/BDF and others;
- AI tools: restricted tools exposed to the built-in assistant.

First-party and third-party modules share one contract: a separate Python process, stdio JSON-RPC, and permission-by-permission declarations. Modules can be uninstalled and replaced, and you decide whether their data is kept or deleted.

## 2. Two indexes, three sources

| Source | What it contains | Manually reviewed |
|---|---|---|
| Official index | First-party modules plus verified third-party adapters; first-party modules are listed first | First-party is maintained by the project; third-party is automatically scanned and verified |
| Community index | Community submissions; proprietary or paid modules are allowed and clearly labelled | No manual review, automated scanning only |
| Local `.ehmod` | A package you obtained elsewhere, installed offline | None — verify the source yourself before installing |

In the app, official and community are two tabs whose counts match this website. Community modules always show "Unreviewed". Scan results are green, yellow, orange or red: red refuses installation; yellow and orange install with a clear warning.

## 3. Installing

### From the in-app marketplace

1. Open Modules → Marketplace;
2. Choose the official or community index and search or filter;
3. Open a module and read what it does, its inputs/outputs and limits;
4. Check permissions, dependencies, licence and SHA-256;
5. Install and approve each permission on the confirmation page.

The first install of a module with dependencies creates a dedicated venv and downloads Python packages, which can take a while.

### From a local `.ehmod`

1. Obtain the `.ehmod` file (a ZIP package);
2. Open Modules → Install from local file;
3. Select it and check the ID, version, permissions and licence in the manifest;
4. Confirm.

The installer checks path traversal, symlinks, unpacked size and `checksums.json`. A failed check aborts the install.

## 4. Reading permissions

Permissions are granted only at install or upgrade time. New permissions on upgrade must be re-approved and are never inherited.

| Permission | Risk | Meaning |
|---|---|---|
| `records:read` | Low | Read records, measurements and analysis results |
| `records:write` | Medium | Create or update records |
| `records:delete` | High | Delete records; never granted by default |
| `files:user-selected` | Low | Read files you explicitly choose |
| `files:export` | Medium | Write to an export directory you confirm |
| `network` | High | Access the concrete hosts listed in `allowedHosts` |
| `llm` | Medium | Call the LLM you configured |
| `models:download` | Medium | Download model weights |
| `ui:custom` | High | Provide custom UI inside a sandbox |
| `system:notify` | Low | Send system notifications |
| `system:background` | Medium | Keep running when minimised |

Rules of thumb:

- a module that only reads data but asks for `records:delete`: refuse it or choose another;
- a module that only handles local files but asks for `network`: check which hosts it needs;
- `ui:custom` means the module ships its own UI and carries more risk; only trust it from a known source.

## 5. Data and privacy

- Health data stays on your machine by default; the app sends no telemetry and does not report installed modules;
- module logs must not contain waveforms, notes or original filenames;
- export and reports happen only when you trigger them;
- you choose whether a module's data is kept or deleted on uninstall;
- all analysis output is non-medical and not for diagnosis or treatment.

## 6. The module you want does not exist?

At the bottom of the marketplace there is a "Can't find the module you need?" form. Fill in the module name, purpose, inputs, outputs and the data/permissions it needs, and it generates a prompt:

1. Copy the prompt and paste it into your own AI agent (Claude Code, Cursor, Codex, and so on);
2. The agent follows the eclipse health module contract to produce `module.json`, worker code, tests and a packaging script;
3. Take the resulting `.ehmod` package and use Install from local file in the app.

The fuller development reference is the [agent module design guide](modules-agent-guide.en.md) — hand it straight to your agent.

## 7. FAQ

**The install failed.**
Check the error code first. Dependency failures are usually network or version conflicts; `MODULE_CRASH` means the worker exited at startup — check its log.

**The update asks for a new permission.**
You must re-approve it. If you decline, stay on the old version or uninstall.

**Are community modules safe?**
The community index is automatically scanned, not manually reviewed. Read the author, repository, permissions and scan result, and read the source if you need to.

**Can two engines of the same kind coexist?**
Yes. Analysis-model modules can usually be switched or compared side by side; the core still enforces which records each module may write.

**Can a module read all my records?**
Only with `records:read`. A module can only read and write records it created, or records covered by the `recordTypes` it declares.

## 8. Links

- Marketplace: https://eclipse-health.fit/en/modules.html
- Developer docs: https://eclipse-health.fit/en/developers.html
- Agent design guide: https://eclipse-health.fit/docs/modules-agent-guide.en.md
- Source and submissions: https://github.com/Muhan-Qiu/ecg-agent
- Licence: the core is GPL-3.0-only; module licences are declared in each manifest.
