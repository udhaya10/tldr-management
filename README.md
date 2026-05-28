# tldr-management

A Django-based management layer that keeps [tldr-code](https://github.com/udhaya10/tldr-code)'s
caching subsystems healthy, indexes your repo in real time, and gives you a
single dashboard to see what your code intelligence is doing.

> One command at the start of the working day. Everything else is automatic.

---

## What is this?

[tldr-code](https://github.com/udhaya10/tldr-code) is a fantastic Rust CLI
for code intelligence — but it ships three independent caches (Salsa
in-memory, Salsa on-disk, vector embeddings) that each die or degrade in
different ways if you don't manage them manually:

| Cache | Dies when | Consequence |
|---|---|---|
| Salsa in-memory | Daemon idle 30 min | 8 structural commands lose ~35× speedup |
| Salsa on-disk | (survives, must be re-warmed) | Slow daemon rebuild |
| Vector embeddings | Cold start, never indexed | `tldr semantic` blocks for 36+ min |

**`tldr-management`** is the long-running service that takes care of all
three for you. It:

- Starts and warms the `tldr` daemon when you begin work.
- Monitors the daemon every 10 minutes and restarts it if it dies.
- Watches your source tree with kernel-level file events (a small C
  helper binary) and re-embeds files within **~2 seconds** of being
  saved — no polling, no idle CPU burn.
- Tracks per-file embed state so re-indexes are incremental.
- Shows you a live dashboard of daemon health, embed cache state, recent
  events, and upcoming scheduled work.

---

## Architecture at a glance

```diagram
╭────────────────────────────────────────────────────────────╮
│  tldr-code  (Rust CLI — kept clean, only called via its    │
│  public CLI; no internal coupling)                         │
╰────────────────────────┬───────────────────────────────────╯
                         │ subprocess: `tldr <cmd> --json`
                         ▼
╭────────────────────────────────────────────────────────────╮
│                    tldr-management  (this repo)            │
│                                                            │
│   ╭──────────────╮   events   ╭───────────╮   subprocess   │
│   │  fs watcher  │───────────▶│  Django   │───────────────▶│──▶ tldr embed
│   │  (C binary)  │            │  service  │                │   tldr warm
│   ╰──────────────╯            │           │                │   tldr daemon
│                               │  SQLite + │                │
│                               │  scheduler│                │
│                               │  + HTMX UI│                │
│                               ╰─────┬─────╯                │
│                                     ▼                      │
│                              ╭────────────╮                │
│                              │ Dashboard  │ http://...:8765│
│                              ╰────────────╯                │
╰────────────────────────────────────────────────────────────╯
```

This is a **sidecar / wrapper architecture**. We never modify `tldr-code`
itself — we only call its public CLI. That keeps the CLI as a stable
contract and means our management layer evolves independently of the
underlying tool.

---

## Why Django?

Most of what this service does is slow (sub-second, not microsecond):
running subprocesses, writing to SQLite, rendering a dashboard. The
performance-critical part — watching the filesystem for changes — is
delegated to a tiny C binary that runs at kernel speed.

That makes Django a sensible choice for the orchestration layer:

| What we get from Django | Why it matters |
|---|---|
| **ORM + migrations** | Schema evolves cleanly as we add features |
| **Admin interface** | Free debugging UI for service state, file tracking, and event logs |
| **Management commands** | `manage.py service-start`, `service-stop`, `service-status` — the entire CLI is just well-organized commands |
| **DRF API** | JSON endpoints for the dashboard, automation, and CI hooks |
| **HTMX-friendly templates** | Build the status dashboard without writing a SPA |
| **Mature signal/lifecycle handling** | No reinventing graceful shutdown |

The performance "cost" of Django (a few ms of request overhead) is
irrelevant when the actual work — `tldr embed` of a changed file — takes
100–500 ms in Rust.

### Library choices (deliberately minimal)

| Package | Version | Purpose |
|---|---|---|
| `django` | `6.0.5` | Web framework |
| `djangorestframework` | `3.17.1` | JSON API for the dashboard + automation |
| `cashews` | `7.5.0` | Async caching layer (cache `tldr daemon status`, file MD5 lookups) |
| `filelock` | `3.29.0` | Cross-process PID lock for the long-running service |
| `tenacity` | `9.1.4` | Retry decorator for flaky `subprocess.run(["tldr", ...])` calls |
| `python-dotenv` | `1.2.2` | Load configuration from `.env` files |

That's it — seven dependencies total (including Django itself).

**What we deliberately do NOT pull in:**

| Excluded | Why not |
|---|---|
| **Celery / Redis / RabbitMQ** | Adds a broker we don't need. |
| **Procrastinate / Django-Q / Huey** | Background-job frameworks. We're a single long-running process with two timers (10 min health check, debounced embed). Python stdlib `threading.Timer` handles this in ~30 lines. |
| **PostgreSQL / psycopg / psycopg-pool** | We are a **single-user local service**. SQLite is sufficient and ships with Python. No external database server. |
| **Channels / Daphne / Uvicorn** | The dashboard works fine over plain WSGI. WebSocket live-updates can be added later as an optional extra if anyone wants them. |

### Database — SQLite only

`tldr-management` runs as a **single-user local service**, so we use
**SQLite** (via Django's default backend) and only SQLite. Hard
requirement: **no PostgreSQL, no external database server, ever**.

Everything lives in a single `state.db` file under `.tldr-svc/`:

- Service state (daemon PID, last warm time, embed status)
- Per-file embed tracking (path, MD5, last-embedded timestamp)
- Append-only event log

This keeps the runtime footprint to: **Python + one SQLite file + one
compiled C binary**. No server processes besides the `tldr` daemon
itself. The whole thing can be deleted with `rm -rf .tldr-svc/`.

---

## Features

- ✅ **Event-driven re-indexing** — file saved → embedded in <3 s, no polling
- ✅ **Daemon watchdog** — auto-restart on failure, configurable cadence
- ✅ **Incremental embeds** — per-file MD5 tracking, skips unchanged files
- ✅ **Persistent state** — SQLite via Django ORM, survives restarts
- ✅ **Live dashboard** — daemon status, cache state, recent events, ETA to
  next scheduled work
- ✅ **Health checks** — 10-minute heartbeat keeps daemon alive through the
  30-minute idle timeout
- ✅ **Append-only event log** — full history of `start`, `stop`,
  `daemon_restart`, `embed_done`, `health_ok`, `health_fail`, `error`
- ✅ **Zero coupling to `tldr-code` internals** — only the public CLI is used
- ✅ **Cross-platform file watching** — Linux (inotify), macOS (FSEvents),
  Windows (ReadDirectoryChangesW)

---

## Requirements

- **Python 3.14+** (latest stable, currently `3.14.5`)
- **Django 6.0+** (latest stable, currently `6.0.5`) — installed via `pip`
- [tldr-code](https://github.com/udhaya10/tldr-code) installed and on `$PATH`
- **`clang`** — the C compiler we use to build the bundled file-watcher
  binary (one-time, ~1 second). See platform install steps below.
- SQLite (bundled with Python)

We track the **latest stable** releases of both Python and Django and pin
the minimum versions accordingly. Older Python (3.13 and below) and older
Django (5.2 LTS and below) are not supported — we trade backward
compatibility for access to the newest performance and type-hint features.

No other system dependencies. Django and its supporting packages are
installed via `pip`:

```bash
pip install "Django>=6.0,<7.0"
```

### Why `clang`?

`clang` is the only C compiler available with a **single official install
step on all three platforms**. We standardize on it so the build script,
flags, and error messages are identical everywhere — Windows, macOS, and
Linux users follow the same instructions. No `gcc`/`cl.exe`/MSVC
detection branches, no per-platform makefiles.

### Installing `clang`

| Platform | Install command |
|---|---|
| **macOS** | `xcode-select --install`  *(ships clang via Xcode Command Line Tools)* |
| **Linux — Debian/Ubuntu** | `sudo apt install clang` |
| **Linux — Fedora/RHEL** | `sudo dnf install clang` |
| **Linux — Arch** | `sudo pacman -S clang` |
| **Windows** | Install [MSYS2](https://www.msys2.org/) then run `pacman -S mingw-w64-x86_64-clang`  *(or use the official LLVM Windows installer from [releases.llvm.org](https://releases.llvm.org/))* |

Verify with:

```bash
clang --version
```

> The watcher is ~500 lines of portable C99. `clang` compiles it in under
> a second. No CMake, no autotools, no MSBuild — just `clang` and a single
> shell/PowerShell script.

---

## Quick start

```bash
# 1. Clone and set up
git clone <this repo>
cd tldr-management
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. Build the bundled file-watcher C binary for your platform (one-time)
./scripts/build-watcher.sh

# 3. Initialize the database
python manage.py migrate

# 4. Start the service (long-running)
python manage.py service-start

# 5. (In another shell) View the dashboard
open http://localhost:8765
```

That's it. The service now:

- Started the `tldr` daemon and warmed its caches.
- Began watching configured source directories for file changes.
- Kicked off a background embed if the embedding cache was cold.
- Will run a daemon health check every 10 minutes.

---

## Management commands

All operations are exposed as Django management commands:

```bash
python manage.py service-start             # Start the long-running service
python manage.py service-stop              # Graceful shutdown
python manage.py service-status            # Human-readable status
python manage.py service-restart           # Stop + start
python manage.py reindex --full            # Force full re-embed of all watched roots
python manage.py reindex --since 1h        # Re-embed files modified in the last hour
python manage.py dashboard                 # Start the web dashboard (port 8765)
python manage.py doctor                    # Verify environment, paths, watcher, tldr version
```

---

## Status output (target UX)

```
$ python manage.py service-status

tldr-management  ●  running  (PID 12345, uptime 2h 14m)

  Daemon       ✓  running          (last restart: 08:32)
  Salsa warm   ✓  ready            (warmed at 08:32, 10 min ago)
  Embed cache  ✓  warm             (3,412 chunks, last indexed 19:41 yesterday)
  Watcher      ✓  2 roots          (backend/, webui/src/)

  Pending re-embed:    0 files
  Next health check:   in 4 min
  Watcher events/min:  3.2 (rolling avg)

  Recent events:
    11:30  health_ok       daemon alive
    11:24  embed_done      1 file, 7 chunks, 412 ms
    11:24  fs_change       backend/auth/views.py
    11:20  health_ok       daemon alive
    11:10  embed_skip      no changed files
    08:32  warm            1.2 s, 4 caches populated
    08:32  daemon_start
    08:31  start
```

---

## Configuration

Configuration lives in `tldr_management/settings.py` and an optional
`.tldr-svc/config.toml` override file. Sensible defaults are shipped; the
common knobs are:

| Setting | Default | Purpose |
|---|---|---|
| `WATCHED_ROOTS` | `["backend/", "webui/src/"]` | Directories to watch and re-embed |
| `WATCHED_EXTENSIONS` | `[".py", ".ts", ".tsx"]` | File types to track |
| `EMBED_DEBOUNCE_SECONDS` | `2.0` | Coalesce multiple saves into one embed |
| `DAEMON_HEALTH_INTERVAL` | `600` | Daemon health check cadence (seconds) |
| `DASHBOARD_PORT` | `8765` | Where to bind the web UI |
| `TLDR_BINARY` | `tldr` | Path to the `tldr` CLI (auto-discovered if on `$PATH`) |
| `WATCHER_BINARY` | `.tldr-svc/watcher` | Path to the compiled file-watcher helper |

---

## Project layout

```
tldr-management/
├── README.md                          ← this file
├── manage.py
├── requirements.txt
├── pyproject.toml
├── tldr_management/                   ← Django project root
│   ├── settings.py
│   ├── urls.py
│   └── asgi.py
├── service/                           ← Django app: the long-running service
│   ├── apps.py
│   ├── models.py                      ← ServiceState, FileEmbedState, ServiceLog
│   ├── management/commands/
│   │   ├── service_start.py
│   │   ├── service_stop.py
│   │   ├── service_status.py
│   │   ├── reindex.py
│   │   ├── dashboard.py
│   │   └── doctor.py
│   ├── watcher.py                     ← File-watcher client
│   ├── scheduler.py                   ← EmbedScheduler + DaemonWatchdog
│   ├── tldr_cli.py                    ← typed subprocess wrappers around `tldr`
│   └── views.py                       ← dashboard views (HTMX)
├── scripts/
│   ├── build-watcher.sh               ← compiles the vendored watcher C source
│   └── ...
├── vendor/
│   └── watcher-src/                   ← C source for the native file watcher
└── .tldr-svc/                         ← runtime artifacts (gitignored)
    ├── watcher                        ← compiled binary
    ├── state.db                       ← SQLite (Django default)
    ├── service.pid
    └── service.log
```

---

## Design principles

1. **The CLI is the only contract.** We never depend on `tldr-code`'s Rust
   internals — only on `tldr <cmd> --json` output.
2. **Parse structured output only.** No scraping of human-readable text.
3. **State belongs to us.** All persistent state lives in our SQLite DB.
   We never write inside directories owned by `tldr-code`.
4. **Workarounds live here.** When `tldr` lacks a feature we need, we
   implement it in our layer.
5. **Reversibility.** Every workaround must be removable if `tldr-code`
   adopts the feature natively.
6. **Vendor-neutral telemetry.** The service emits standard
   OpenTelemetry traces, metrics, and logs over OTLP. It never imports
   from, links to, or depends on any specific backend (HyperDX, Aspire,
   SigNoz, Jaeger, DataDog, Honeycomb, …). The backend is selected
   purely via the `OTEL_EXPORTER_OTLP_ENDPOINT` environment variable.

These rules keep `tldr-management` evolving independently of the underlying
CLI, and keep `tldr-code` clean and idiomatic.

---

## Observability (optional)

`tldr-management` emits **standard OpenTelemetry** — nothing more.
You can point it at any OTLP-compatible backend without touching code.

### What gets instrumented

- **Traces** — one span per management command, subprocess call to
  `tldr`, file-watcher event, debounce cycle, and embed batch
- **Metrics** — request counters, embed duration histograms, daemon
  health-check success rate, watcher events per minute, debounce queue
  depth
- **Logs** — Django log records with `trace_id` / `span_id` injected for
  correlation

### Dependencies (only if you opt into telemetry)

| Package | Purpose |
|---|---|
| `opentelemetry-distro` | Auto-configures SDK from environment variables |
| `opentelemetry-exporter-otlp` | Sends data via OTLP (gRPC or HTTP) — the only wire format we support |
| `opentelemetry-instrumentation-django` | Auto-spans every Django request |
| `opentelemetry-instrumentation-logging` | Inject trace IDs into logs |

These are **optional** — install only if you want telemetry. The service
runs identically without them; OTel becomes a no-op.

### Configuration — backend-agnostic

The service knows nothing about which backend you use. Everything is
driven by standard OTel environment variables:

```bash
# Required: where to send the data
export OTEL_EXPORTER_OTLP_ENDPOINT="http://localhost:4317"

# Optional: identify this instance
export OTEL_SERVICE_NAME="tldr-management"
export OTEL_RESOURCE_ATTRIBUTES="deployment.environment=local,host.name=$(hostname)"

# Optional: which signals to emit
export OTEL_TRACES_EXPORTER="otlp"
export OTEL_METRICS_EXPORTER="otlp"
export OTEL_LOGS_EXPORTER="otlp"
```

Want to swap backends? Change `OTEL_EXPORTER_OTLP_ENDPOINT`. That's
the entire migration. No code changes, no rebuilds, no service restart
beyond reading the new env var.

### Backends known to work (any OTLP receiver does)

- **HyperDX**, **SigNoz**, **Uptrace**, **OpenObserve** — open-source,
  self-hosted, all-in-one
- **Aspire Dashboard** — Microsoft, ephemeral local dev
- **Jaeger** (traces only), **Prometheus** (metrics only) — classic
  single-signal backends
- **Grafana Tempo / Mimir / Loki** — full LGTM stack
- **Honeycomb**, **DataDog**, **New Relic**, **Grafana Cloud**, **Axiom** —
  hosted SaaS

We do not test against, recommend, or favor any one of these. Pick what
fits your workflow.

### Design rule for contributors

If you ever find yourself writing code like this, **stop**:

```python
# ❌ NEVER do this
import hyperdx
hyperdx.configure(api_key="...")

# ❌ Also never
if BACKEND == "signoz":
    add_signoz_specific_attributes(span)
```

Always do this instead:

```python
# ✅ Standard OTel only
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("tldr.embed", attributes={
    "tldr.path": path,
    "tldr.langs": langs,
}) as span:
    result = subprocess.run(...)
    span.set_attribute("tldr.exit_code", result.returncode)
```

If a backend ever requires a vendor-specific SDK to function, we drop
that backend, not our neutrality.

---

## Logging

`tldr-management` keeps logging deliberately simple: **Python's standard
library `logging` module**, optionally enhanced with JSON formatting and
automatic OTel trace-correlation. No `loguru`, no `structlog`, no
parallel logging system.

### Two distinct concerns

We separate **application logs** from the **event log**. They serve
different purposes and live in different places:

| | **Application logs** | **Event log** |
|---|---|---|
| Purpose | Debug / diagnose code paths | Audit trail of domain events |
| Examples | `"starting watcher thread"`, `"subprocess exited 0"`, `"retry attempt 2"` | `daemon_start`, `embed_done`, `health_fail` |
| Format | JSON (production) or plain text (dev) | Strict schema in SQLite |
| Where | stdout + rotating file + OTel (optional) | SQLite `service_log` table |
| Surfaced in | Console, log files, observability backend | `service-status` dashboard, admin UI |
| Mutability | Append-only stream | Append-only table |

This section is about **application logs**. The event log is described
in the `models.py` schema.

### The three-layer stack

```diagram
╭─────────────────────╮  ╭──────────────────────╮  ╭───────────────────╮  ╭──────────╮
│  logger.info("...") │─▶│ stdlib creates       │─▶│ OTel handler      │─▶│ JSON     │─▶ stdout
│  (your code uses    │  │ LogRecord with msg,  │  │ enriches record   │  │ formatter│   file
│  stdlib `logging`)  │  │ level, args, time    │  │ with trace_id +   │  │ serializes│   OTel
│                     │  │                      │  │ span_id from      │  │ to JSON  │
│                     │  │                      │  │ active context    │  │          │
╰─────────────────────╯  ╰──────────────────────╯  ╰───────────────────╯  ╰──────────╯
       API layer              core stdlib              enrichment             output
```

Each layer has exactly one job. Together they give us structured,
trace-correlated, JSON-formatted logs **without replacing the stdlib API
that Django, DRF, and OTel all expect**.

| Layer | Library | Required? | Replaces stdlib? |
|---|---|---|---|
| API + core | Python `logging` (stdlib) | yes (built in) | — |
| Trace enrichment | `opentelemetry-instrumentation-logging` | optional (only with telemetry) | no, extends stdlib |
| JSON formatting | `python-json-logger` (~30 KB) | optional (only for JSON output) | no, just a formatter |

If you skip the optional pieces, logging still works — you just get
plain text and no trace IDs.

### What a log line looks like

A single call inside an active span:

```python
logger.info("embedding file %s", path, extra={"chunks": 7})
```

…produces this JSON line on stdout, in the rotating file, and shipped
over OTLP:

```json
{
  "asctime": "2026-05-28T11:24:13.412Z",
  "name": "service.scheduler",
  "levelname": "INFO",
  "message": "embedding file backend/auth/views.py",
  "chunks": 7,
  "otelTraceID": "4bf92f3577b34da6a3ce929d0e0e4736",
  "otelSpanID": "00f067aa0ba902b7",
  "otelServiceName": "tldr-management"
}
```

The `otelTraceID` matches the trace ID shown in your observability
backend, so you can pivot from a span in HyperDX (or any backend)
straight to the log lines emitted during that span — and vice versa.

### Destinations

| Sink | Purpose | Format |
|---|---|---|
| **stdout** | Live tail during dev (`tail -f` or terminal scrollback) | JSON (prod) / plain (dev) |
| **`.tldr-svc/service.log`** | Post-mortem on disk, rotated at 10 MB × 5 files | JSON |
| **OTLP exporter** | Ships to your observability backend, correlated with traces | OTel log records |

OTLP shipping is **disabled** unless `OTEL_EXPORTER_OTLP_ENDPOINT` is
set, matching the rest of the telemetry stack.

### Log levels

| Level | When to use | Example |
|---|---|---|
| `DEBUG` | Detailed flow tracing, off by default | "fsnotifier event: CHANGE backend/views.py" |
| `INFO` | Significant lifecycle steps | "embedded 1 file, 7 chunks, 412 ms" |
| `WARNING` | Recoverable issue, no user action required | "daemon health check failed, retrying" |
| `ERROR` | Operation failed, user-visible | "tldr embed exited with code 1" |
| `CRITICAL` | Service-fatal, will exit | "cannot acquire PID lock, another instance running" |

Default level is `INFO`. Override via the `LOG_LEVEL` environment
variable.

### Configuration

All configuration lives in `tldr_management/settings.py` as a Django
`LOGGING` dict:

```python
# tldr_management/settings.py

import os

LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_FORMAT = os.environ.get("LOG_FORMAT", "json")  # "json" or "plain"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": (
                "%(asctime)s %(name)s %(levelname)s %(message)s "
                "%(otelTraceID)s %(otelSpanID)s %(otelServiceName)s"
            ),
        },
        "plain": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": LOG_FORMAT,
        },
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": ".tldr-svc/service.log",
            "maxBytes": 10_000_000,
            "backupCount": 5,
            "formatter": "json",
        },
    },
    "root": {
        "handlers": ["console", "file"],
        "level": LOG_LEVEL,
    },
}

# Trace-correlation handler (only when OTel telemetry is enabled)
if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    LoggingInstrumentor().instrument(set_logging_format=False)
```

That's the entire wiring. ~30 lines of config gives you JSON output +
trace correlation + rotating files + console output + level control.

### Usage in code

Use stdlib `logging` directly — no wrappers, no helpers:

```python
# service/scheduler.py

import logging

logger = logging.getLogger(__name__)   # "service.scheduler"

def embed_file(path: str) -> None:
    logger.info("embedding file %s", path)
    try:
        result = run_tldr_embed(path)
        logger.info("embed done", extra={"chunks": result.chunks,
                                          "latency_ms": result.latency_ms})
    except subprocess.CalledProcessError as e:
        logger.error("tldr embed failed", extra={"exit_code": e.returncode,
                                                  "stderr": e.stderr})
```

The `extra=` dict appears as top-level fields in the JSON output — no
need for `f"..."` string interpolation of structured data.

### Why not `loguru`, `structlog`, or others?

| Library | Why not for us |
|---|---|
| **loguru** | Pretty syntax, but creates a parallel logging system. Django, DRF, and OTel all hook into stdlib `logging`; bridging loguru back is fragile. |
| **structlog** | Excellent, but adds a key-value pipeline we don't need. OTel span attributes already cover structured context. |
| **picologging** | ~5 % faster, but a C extension with no benefit at our log volume. |

Stdlib `logging` is the **only logger that Django, DRF, OpenTelemetry,
and every Python tool agrees on natively**. Sticking with it means zero
impedance mismatch.

### Dependency summary

| Package | Required? | Size | Purpose |
|---|---|---|---|
| `logging` (stdlib) | yes | — | API + core |
| `python-json-logger` | optional | ~30 KB | JSON output format |
| `opentelemetry-instrumentation-logging` | optional | ~50 KB | Trace ID injection |

Without the optional packages, logs are plain text and uncorrelated —
still useful, still complete. Adding them is two `pip install` commands
and one env var.

---

## Roadmap

- **Phase 1** — Django scaffold, models, basic `service-start`/`stop`/`status`
- **Phase 2** — Daemon watchdog (10-min heartbeat, auto-restart)
- **Phase 3** — Cold-start background embed + status tracking
- **Phase 4** — File-watcher integration, event-driven re-embeds, debouncing
- **Phase 5** — HTMX dashboard with live updates
- **Phase 6** — Configurable roots, shell hooks, multi-project support

---

## License

Apache 2.0.

---

## Credits

This project is a management layer for
**[tldr-code](https://github.com/parcadei/tldr-code)**, originally
authored by **[parcadei](https://github.com/parcadei)**. All credit for
the underlying code-intelligence engine, its Rust implementation, and the
ideas that make it valuable goes to the original author.

`tldr-management` exists only to orchestrate and operationalize that
excellent tool — it adds no intelligence of its own beyond lifecycle
management, file-event-driven re-indexing, and a status dashboard.
