# Contributing to eclipse health

Thanks for considering a contribution. This project is deliberately small at the core and modular everywhere else — most improvements belong in a module rather than in core code.

## Ways to help

- **Report a bug** — use the bug report issue template. Include the app version, Windows version, and steps to reproduce. Please do **not** attach real health data; synthetic or redacted files are enough.
- **Suggest a feature** — use the feature request template. Explain the problem first, the proposed solution second.
- **Build a module** — device adapters, analysis engines, health domains, UI widgets, exporters and AI tools all fit the module contract.
- **Translate or fix docs** — most design documents under `docs/` are in Chinese; English translations are welcome.
- **Improve the core** — bug fixes, performance work and test coverage are always useful.

## Module authors

Read, in this order:

1. [`docs/MODULE_CONTRACT_V1.md`](docs/MODULE_CONTRACT_V1.md) — package format, RPC, permissions, lifecycle.
2. [`docs/MODULE_CONTRACT_V2.md`](docs/MODULE_CONTRACT_V2.md) — contribution points.
3. [`docs/MODULE_DEVELOPER_GUIDE_V1.md`](docs/MODULE_DEVELOPER_GUIDE_V1.md) — end-to-end walkthrough with examples.
4. [`marketplace/CONTRIBUTING.md`](marketplace/CONTRIBUTING.md) — marketplace submission flow.

Rules that matter:

- Module IDs are bound to GitHub identity: `io.github.<owner>.<name>`.
- Modules run in their own process and must not import core Python code.
- Declare the minimum permissions you need. New permissions on upgrade force users to re-approve.
- Only OSI-approved open-source modules are accepted into the official index. The community index allows proprietary modules with clear labelling.
- Packages are scanned automatically. Red results block installation.

## Core contributors

1. Read [`BUILD.md`](BUILD.md).
2. Install Node.js 20.19+ and Python 3.12, then run the checks below.
3. Keep changes focused; include tests for bug fixes and new behaviour.
4. Open a pull request against `main`.

```powershell
npm run build
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
backend\.venv\Scripts\python.exe -m ruff check backend
```

## Commit style

Use short imperative subjects, optionally with a Conventional Commit prefix:

```
feat: add Huawei health import preview
fix: keep waveform zoom after lead switch
docs: translate module contract section 4
```

## Security

Do not open a public issue for security problems. See [`SECURITY.md`](SECURITY.md).

## License

By contributing, you agree that your contribution is licensed under the project's GPL-3.0-only license, unless a module declares its own compatible license.
