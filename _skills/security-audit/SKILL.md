# Security Audit Protocol

You are acting as a **Senior Security Analyst** and **Network Security Engineer** performing a comprehensive security audit on a codebase. This is a full-spectrum review — treat this as a professional penetration test report combined with a secure code review.

## Two Modes

### Quick Mode (during development)

Triggered by: "quick check" or "quick audit"

Fast, non-blocking scan (<5 seconds). Checks only:
1. **Secrets detection** — scan for hardcoded API keys, tokens, passwords, connection strings in code
2. **Gitignore validation** — verify `.gitignore` exists and covers `.env`, `*.key`, `*.pem`, `node_modules/`, `venv/`, `__pycache__/`

Report findings inline (no SECURITY_AUDIT.md generated). Non-blocking — reports but doesn't stop anything.

### Full Mode (before deploy)

Triggered by: "audit", "security audit", or automatically by the deploy skill

Runs all phases below. Generates `SECURITY_AUDIT.md` in the project root. Blocking — if CRITICAL or HIGH findings exist, recommend aborting deploy.

### When each mode runs
- **Quick**: on demand via "quick check" alias, optionally on every `start.bat` launch
- **Full**: automatically before deploy skill runs, on demand via "audit" alias

---

## How to Use This Protocol

Point Claude Code at a project directory and say:

```
Run the security audit protocol against this codebase
```

For quick mode:

```
Quick check this codebase
```

---

## Full Mode — Execution Instructions

1. **Read this entire protocol before starting.**
2. **Work phase by phase.** Do not skip phases. Each phase catches different vulnerability classes.
3. **Use parallel tool calls** within each phase to maximize speed.
4. **Log every finding** with severity, file path, line number, and remediation.
5. **At the end**, produce a structured report in the project directory as `SECURITY_AUDIT.md`.
6. If the codebase is large, prioritize: entry points > auth > data handling > config > dependencies > internal logic.

---

## Phase 1: Reconnaissance — Understand the Attack Surface

Before testing, map the codebase.

### 1.1 Technology Stack Identification
- Identify languages, frameworks, package managers (package.json, requirements.txt, pyproject.toml, Cargo.toml, go.mod, etc.)
- Identify web servers, databases, message queues, caches
- Identify cloud/infra config (Dockerfile, docker-compose, terraform, k8s manifests, CI/CD configs)

### 1.2 Entry Point Mapping
- Find all HTTP/WebSocket route definitions (Flask routes, Express routes, FastAPI endpoints, etc.)
- Find all CLI entry points (argparse, click, sys.argv usage)
- Find all scheduled tasks, background workers, cron jobs
- Find all file I/O operations (read/write to disk)
- Find all IPC/socket/subprocess usage

### 1.3 Data Flow Mapping
- Trace user input from entry points through processing to storage/output
- Identify all trust boundaries (user input → server, server → database, server → external API)
- Note where data crosses trust boundaries without validation

---

## Phase 2: Secrets & Credential Exposure

### 2.1 Hardcoded Secrets Scan
Search for ALL of the following patterns across the entire codebase:

```
# API keys and tokens
grep for: api[_-]?key, api[_-]?secret, auth[_-]?token, access[_-]?token, bearer, jwt
grep for: password\s*=, passwd\s*=, pwd\s*=, secret\s*=
grep for: private[_-]?key, signing[_-]?key, encryption[_-]?key

# Cloud provider credentials
grep for: AKIA[0-9A-Z]{16}  (AWS access keys)
grep for: aws[_-]?secret, aws[_-]?access
grep for: GOOG[\w]+, gcp[_-]?key, google[_-]?api
grep for: az[_-]?account, azure[_-]?key

# Database connection strings
grep for: mongodb(\+srv)?://, postgres(ql)?://, mysql://, redis://, sqlite:///
grep for: connection[_-]?string, database[_-]?url, db[_-]?url

# Crypto/blockchain
grep for: 0x[a-fA-F0-9]{40,64}  (wallet addresses/private keys)
grep for: mnemonic, seed[_-]?phrase

# Generic high-entropy strings (base64-encoded secrets)
grep for: [A-Za-z0-9+/]{40,}={0,2} in assignment contexts

# Webhook URLs
grep for: hooks\.slack\.com, discord(app)?\.com/api/webhooks
```

### 2.2 Git History Secrets (if .git exists)
```bash
git log --all --diff-filter=D -- "*.env" "*.pem" "*.key" "*credentials*" "*secret*"
git log -p --all -S "password" -S "api_key" -S "secret" -- . | head -200
```

### 2.3 Configuration File Audit
- Check `.env` files are in `.gitignore`
- Check `.env.example` does NOT contain real values
- Verify `config.py` / `settings.py` loads from env vars, not hardcoded
- Check for overly permissive CORS (allow_origins=["*"])
- Check for debug mode enabled in production configs (`DEBUG=True`, `app.run(debug=True)`)

### 2.4 File Permission & Exposure
- Check for sensitive files that could be served (`.env`, `.git/`, `*.pem`, `*.key`, backup files)
- Check static file serving configuration — does it expose parent directories?
- Look for directory traversal possibilities in file-serving code

---

## Phase 3: Injection Vulnerabilities

### 3.1 SQL Injection
- Find ALL database query construction
- Flag any string concatenation or f-string/format-string in SQL queries
- Verify parameterized queries / ORM usage throughout
- Check for raw SQL in ORM escape hatches (`raw()`, `text()`, `execute()`)

### 3.2 Command Injection
- Find ALL `subprocess`, `os.system`, `os.popen`, `exec`, `eval`, `child_process.exec`, `shell=True` usage
- Check if any user input reaches shell commands
- Verify proper escaping/quoting or use of array-form subprocess calls
- Check for template injection in Jinja2/Mako/Pug (server-side template injection - SSTI)

### 3.3 Cross-Site Scripting (XSS)
- Find all places user input is rendered in HTML
- Check for `| safe`, `markupsafe.Markup()`, `dangerouslySetInnerHTML`, `innerHTML`
- Verify Content-Security-Policy headers
- Check for reflected XSS in error messages, search results, URL parameters
- Check for stored XSS in database-backed content displayed to users

### 3.4 Path Traversal
- Find all file operations that use user-supplied paths
- Check for `../` traversal protection
- Verify `os.path.join` is used with proper base path validation
- Check `send_file`, `send_from_directory`, `static_folder` configurations

### 3.5 Server-Side Request Forgery (SSRF)
- Find all outbound HTTP requests (requests, httpx, fetch, axios, urllib)
- Check if any URL components come from user input
- Verify URL validation blocks internal/private IP ranges (127.0.0.1, 10.x, 172.16-31.x, 192.168.x, ::1)
- Check for DNS rebinding protection

### 3.6 NoSQL Injection
- If MongoDB/DynamoDB/etc., check for unvalidated query operators (`$gt`, `$ne`, `$regex`, etc.)
- Verify input types are enforced (not passing objects where strings expected)

### 3.7 Code Injection / Deserialization
- Find `pickle.loads`, `yaml.load` (unsafe), `eval()`, `exec()`, `Function()`, `new Function()`
- Find `JSON.parse` on untrusted data without schema validation
- Check for insecure deserialization (Python pickle, Java serialization, PHP unserialize)
- Flag any `__import__`, `importlib`, or dynamic module loading from user input

---

## Phase 4: Authentication & Authorization

### 4.1 Authentication Mechanisms
- Identify auth method (JWT, session cookies, API keys, OAuth, basic auth)
- Check for missing auth on sensitive endpoints
- Verify password hashing (bcrypt/argon2/scrypt, NOT md5/sha1/sha256)
- Check for timing-safe comparison on tokens/passwords
- Look for auth bypass via parameter manipulation

### 4.2 Session Management
- Check session token entropy and generation
- Verify session expiration and rotation
- Check for session fixation vulnerabilities
- Verify secure cookie flags (HttpOnly, Secure, SameSite)

### 4.3 Authorization / Access Control
- Check for IDOR (Insecure Direct Object Reference) — can user A access user B's resources?
- Verify role-based access control is enforced server-side, not just client-side
- Check for privilege escalation paths
- Verify API rate limiting exists on auth endpoints

### 4.4 Cryptographic Weaknesses
- Check for weak algorithms (MD5, SHA1 for security purposes, DES, RC4)
- Verify TLS/SSL configuration (no SSLv3, TLS 1.0/1.1)
- Check for hardcoded IVs, weak random number generation (`random` instead of `secrets`)
- Verify Ed25519/RSA key sizes are adequate

---

## Phase 5: Network & Infrastructure Security

### 5.1 Server Configuration
- Check bound addresses (`0.0.0.0` vs `127.0.0.1`) — services that should be local-only
- Check for exposed debug ports, admin panels, health endpoints with sensitive info
- Verify HTTPS enforcement and HSTS headers
- Check for information leakage in error responses (stack traces, version numbers)

### 5.2 CORS & Headers
- Audit CORS configuration: allowed origins, methods, headers, credentials
- Check security headers: X-Frame-Options, X-Content-Type-Options, Strict-Transport-Security, Content-Security-Policy, Referrer-Policy
- Check for clickjacking protection

### 5.3 WebSocket Security
- Check for missing origin validation on WebSocket connections
- Verify authentication on WebSocket upgrade
- Check for message injection/manipulation

### 5.4 DNS & External Connections
- Catalog all external domains/APIs the application connects to
- Check for certificate validation disabled (`verify=False`, `rejectUnauthorized: false`)
- Check for HTTP (not HTTPS) connections to external services
- Look for proxy/tunnel configurations that bypass security controls

---

## Phase 6: Dependency & Supply Chain Security

### 6.1 Known Vulnerabilities
```bash
# Python
pip audit (or safety check)

# Node.js
npm audit

# General
Check versions against known CVE databases
```

### 6.2 Dependency Review
- Check for pinned vs unpinned dependencies
- Look for suspicious or typosquatted package names
- Check for deprecated packages with known issues
- Verify lockfile exists and is committed (package-lock.json, poetry.lock, etc.)

### 6.3 Build & CI/CD Security
- Check GitHub Actions / CI configs for:
  - Secrets exposed in logs
  - Untrusted input in `run:` commands (injection via PR titles, branch names)
  - Overly permissive permissions
  - Third-party actions pinned by hash vs tag

---

## Phase 7: Data Protection & Privacy

### 7.1 Sensitive Data Handling
- Check for PII logged to console/files (names, emails, IPs, financial data)
- Verify sensitive data is encrypted at rest
- Check for sensitive data in URL query parameters (visible in logs/referer headers)
- Verify proper data sanitization before logging

### 7.2 Error Handling & Information Disclosure
- Check that production error pages don't leak stack traces
- Verify database errors are caught and not passed to clients
- Check for verbose error messages revealing internal paths, versions, or config
- Ensure debug endpoints are disabled in production

---

## Phase 8: Local Machine / Host Security (Windows-specific)

### 8.1 Local Execution Risks
- Check `start.bat` and any `.bat`/`.ps1`/`.sh` scripts for:
  - Unquoted paths (can be hijacked with spaces in directory names)
  - Commands that modify system state (registry, services, firewall)
  - Downloads from untrusted URLs
  - Execution of downloaded scripts without verification
- Check for auto-start mechanisms (registry entries, scheduled tasks, startup folder)

### 8.2 File System Security
- Check file permissions on config files, key files, database files
- Verify temp file usage is secure (using tempfile module, not predictable paths)
- Check for symlink/junction attacks in file operations

### 8.3 Process Security
- Check for processes that run with elevated privileges unnecessarily
- Verify no services listen on all interfaces when local-only is intended
- Check for DLL hijacking potential in Windows environments

---

## Phase 9: Chrome Extension Security (if manifest.json detected)

**Skip this phase if the project is not a Chrome/browser extension.**

### 9.1 Manifest & Permissions Audit
- Read `manifest.json` (v2 or v3) completely
- **Principle of least privilege**: Flag every permission and assess whether it's actually needed
  - `<all_urls>` or `*://*/*` — almost never justified, flag as HIGH
  - `tabs` — can see all open URLs, flag if not core to functionality
  - `webRequest` / `webRequestBlocking` — can intercept/modify ALL traffic
  - `cookies` — access to auth cookies across domains
  - `clipboardRead` / `clipboardWrite` — can steal clipboard contents
  - `nativeMessaging` — can execute local binaries, flag as CRITICAL if present
  - `debugger` — full DevTools protocol access, flag as CRITICAL
  - `management` — can disable/uninstall other extensions
  - `proxy` — can redirect all traffic
  - `storage` vs `storage.sync` — synced storage goes to Google account
- Check `host_permissions` — are they scoped to specific domains or wildcard?
- Check `content_security_policy` — is it present and restrictive?
- Check `externally_connectable` — who can message this extension?
- Check `web_accessible_resources` — are internal files exposed to web pages?
- Verify `update_url` if present — could be used for silent malicious updates

### 9.2 Content Script Security
- Find all content scripts (declared in manifest + programmatic `chrome.scripting.executeScript`)
- **DOM XSS in content scripts**:
  - Check for `innerHTML`, `outerHTML`, `document.write`, `insertAdjacentHTML` with page-derived data
  - Check for `eval()`, `new Function()`, `setTimeout(string)` with page data
  - Content scripts share the DOM with the page — any DOM manipulation with unsanitized page data is XSS
- **Message passing injection**:
  - Check `chrome.runtime.onMessage` / `chrome.runtime.onMessageExternal` handlers
  - Verify message origin is validated (which sender/tab sent it)
  - Check if message data is used in `eval`, DOM insertion, URL construction, or API calls without validation
  - Flag any listener that trusts `message.sender` without verification
- **CSS injection**: Check if content scripts inject CSS from untrusted sources
- **Match patterns**: Are content scripts injected too broadly? (`<all_urls>` vs specific sites)

### 9.3 Background Script / Service Worker Security
- Check for `eval()` or dynamic code execution in the background context
- **Privileged API abuse**: Background has access to all Chrome APIs granted by permissions
  - Verify every `chrome.tabs.executeScript` / `chrome.scripting.executeScript` call validates the target
  - Check `chrome.downloads` usage — can be used to drop files silently
  - Check `chrome.webRequest` listeners — are they modifying headers, redirecting, or injecting?
  - Check `chrome.cookies.getAll` — is it scoping to necessary domains or grabbing everything?
- **Alarm/scheduler abuse**: Check `chrome.alarms` for persistent background tasks that phone home
- **Fetch/XHR from background**: Background scripts can bypass CORS
  - Catalog all outbound requests — what domains, what data is sent
  - Check for data exfiltration patterns (sending tab URLs, page content, cookies to external servers)

### 9.4 Extension-to-Web Communication
- **`window.postMessage`**: Check content scripts that use postMessage
  - Verify `targetOrigin` is set (not `"*"`)
  - Verify received messages check `event.origin`
- **`chrome.runtime.sendMessage` from web pages**: If `externally_connectable` allows websites
  - Verify the background listener validates the sender's origin
  - Check what operations external messages can trigger
- **Shared DOM**: Content scripts run in an isolated world but share the DOM
  - Check for data leakage via DOM attributes, custom events, or global variables
  - Verify content scripts don't expose extension internals to the page

### 9.5 Storage & Data Security
- Check what's stored in `chrome.storage.local` / `chrome.storage.sync`
  - Flag tokens, passwords, API keys, PII stored in extension storage (it's not encrypted)
  - `storage.sync` syncs to Google account — extra sensitive
- Check `localStorage` usage in extension pages — less secure than `chrome.storage`
- Verify no sensitive data in extension's `window.name` or URL parameters
- Check IndexedDB usage for unencrypted sensitive data

### 9.6 Update & Integrity
- If the extension loads remote code (fetching JS and executing it), flag as CRITICAL
  - Manifest V3 bans `eval`/remote code but check for workarounds (dynamic imports, blob URLs, iframes loading remote content)
  - Check for `importScripts()` with remote URLs in service workers
- Check if the extension downloads and executes any scripts/configs from external servers
- Verify Subresource Integrity (SRI) on any loaded external resources
- Check for development/debug code left in (console logging tokens, test API endpoints)

### 9.7 Privacy & Data Collection
- Trace ALL data that leaves the extension to external servers
  - What user data is collected? (browsing history, page content, form data, clicks)
  - Is collection proportional to functionality, or excessive?
  - Is there a privacy policy URL in the manifest?
- Check for fingerprinting (collecting canvas, WebGL, font, screen data)
- Check for tracking pixels or analytics SDKs embedded in the extension
- Verify the extension doesn't inject ads, affiliate links, or tracking into web pages

### 9.8 Chrome Web Store Policy Compliance
- No obfuscated code (CWS will reject)
- Single clear purpose (no bundling unrelated functionality)
- All permissions justified by visible features
- No remote code execution
- No user data collection without disclosure
- No modification of web pages unrelated to extension's stated purpose

---

## Phase 10: Business Logic Vulnerabilities

### 10.1 Race Conditions
- Check for TOCTOU (time-of-check-time-of-use) vulnerabilities
- Look for non-atomic operations on shared resources
- Check for double-spend / double-submit vulnerabilities in financial operations

### 10.2 Input Validation
- Check for missing validation on all user inputs
- Verify numeric bounds checking (integer overflow, negative values where only positive expected)
- Check for Unicode/encoding attacks
- Verify file upload validation (type, size, content, filename)

### 10.3 API Abuse
- Check for missing rate limiting
- Check for resource exhaustion (unbounded queries, large file uploads, zip bombs)
- Check for mass assignment / over-posting vulnerabilities
- Verify pagination limits exist on list endpoints

---

## Phase 11: Automated Scans & Final Verification

### 11.1 Pattern-Based Sweep
Run a final comprehensive grep for dangerous patterns:

```
# Dangerous functions by language
Python: eval, exec, compile, __import__, pickle.loads, yaml.load, subprocess with shell=True, os.system
JavaScript: eval, Function(), child_process.exec, innerHTML, document.write
General: TODO security, FIXME security, HACK, XXX, NOSONAR

# Temporary/debug code left in
console.log with sensitive data, print() with credentials, debugger statements
breakpoint(), pdb.set_trace(), import pdb

# Disabled security
verify=False, ssl=False, check_hostname=False, CSRF_ENABLED=False
@csrf_exempt, no_auth, skip_auth, unsafe
```

### 11.2 Compile the Final Report
Create `SECURITY_AUDIT.md` in the project root with this structure:

```markdown
# Security Audit Report
**Date**: [date]
**Scope**: [project path]
**Auditor**: Claude Code Security Protocol

## Executive Summary
[2-3 sentence overview of security posture]

## Risk Summary
| Severity | Count |
|----------|-------|
| CRITICAL | X |
| HIGH     | X |
| MEDIUM   | X |
| LOW      | X |
| INFO     | X |

## Findings

### [SEVERITY] Finding Title
- **Location**: `file:line`
- **Category**: [Injection / Auth / Secrets / Config / Dependency / etc.]
- **Description**: What the vulnerability is
- **Impact**: What an attacker could do
- **Reproduction**: How to trigger it
- **Remediation**: Exact code changes or configuration needed
- **Status**: Open

[Repeat for each finding, ordered by severity]

## Recommendations
[Prioritized list of security improvements]

## Scope Limitations
[What was NOT tested and why]
```

---

## Severity Definitions

| Severity | Definition |
|----------|-----------|
| **CRITICAL** | Immediate exploitation possible. Remote code execution, credential exposure, auth bypass. Fix immediately. |
| **HIGH** | Significant risk. SQL injection, XSS, SSRF, privilege escalation, exposed secrets. Fix within days. |
| **MEDIUM** | Moderate risk. Missing security headers, weak crypto, information disclosure, missing rate limiting. Fix within weeks. |
| **LOW** | Minor risk. Debug mode, verbose errors in dev config, missing best practices. Fix in normal development cycle. |
| **INFO** | No immediate risk. Suggestions for defense-in-depth, code quality improvements. |

---

## Checklist (verify each item is covered)

- [ ] Hardcoded secrets scan
- [ ] Git history secrets check
- [ ] .env / config file audit
- [ ] SQL injection review
- [ ] Command injection review
- [ ] XSS review
- [ ] Path traversal review
- [ ] SSRF review
- [ ] Deserialization / code injection review
- [ ] Authentication audit
- [ ] Authorization / IDOR audit
- [ ] Session management review
- [ ] Cryptographic review
- [ ] CORS & security headers
- [ ] WebSocket security
- [ ] TLS / certificate validation
- [ ] Dependency vulnerability scan
- [ ] CI/CD security review
- [ ] Sensitive data logging check
- [ ] Error handling / info disclosure
- [ ] Local execution script review
- [ ] Chrome Extension: manifest & permissions audit (if applicable)
- [ ] Chrome Extension: content script XSS & message injection review
- [ ] Chrome Extension: background script privilege audit
- [ ] Chrome Extension: extension-to-web communication review
- [ ] Chrome Extension: storage & data security review
- [ ] Chrome Extension: remote code / update integrity check
- [ ] Chrome Extension: privacy & data collection audit
- [ ] Chrome Extension: Web Store policy compliance
- [ ] Race condition review
- [ ] Input validation review
- [ ] Rate limiting check
- [ ] Dangerous function sweep
- [ ] Report generated
