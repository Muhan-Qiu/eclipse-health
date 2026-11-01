# Security policy

eclipse health handles personal health data and runs third-party modules, so security reports are taken seriously.

## Reporting a vulnerability

**Please do not open a public issue.**

Use GitHub's private vulnerability reporting:

1. Go to the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Describe the issue, the affected version, and reproduction steps using synthetic data.

If private reporting is unavailable, contact the maintainer through their GitHub profile.

Please include, where possible:

- Affected component (core, backend API, module runtime, marketplace, site).
- Version and Windows build.
- Whether exploitation requires local access, a malicious module, or a remote endpoint.
- Any suggested fix or mitigation.

## Scope

In scope:

- The desktop application and its local backend (`127.0.0.1:8765`).
- The module runtime: process isolation, venv handling, permission checks, package extraction.
- The marketplace: index signature verification, checksum handling, scanner bypasses.
- The external API: authentication, key handling, localhost binding.
- Data handling: path traversal, unsafe file writes, leak of health data or API keys.

Out of scope:

- Issues that require an already-compromised machine or admin rights.
- Vulnerabilities in third-party Python packages that are already public and have an upstream fix (report upstream first).
- Social engineering.
- Denial of service against the local app on the same machine.

## Handling

- We acknowledge reports as soon as possible and aim to give an initial assessment within a few days.
- Fixes are prepared privately and released with a credit note unless you prefer to stay anonymous.
- Please give us reasonable time to ship a fix before public disclosure.

## Supported versions

Only the latest release receives security fixes while the project is in alpha.
