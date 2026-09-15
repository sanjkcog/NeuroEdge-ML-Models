---
name: logger_for_app
description: Centralised application logging framework covering log levels (DEBUG/INFO/WARN/ERROR), structured JSON output, contextual enrichment (correlation IDs, request tracing), multi-destination routing, security filtering, and async performance patterns. Includes reference implementations for Python, TypeScript, and Java.
origin: NeuroEdge
---

# Application Logging Framework

A centralised, structured logging interface that every module in an application writes to.
Consistent, machine-parseable logs are the primary observability signal for production systems.

---

## When to Activate

- Setting up logging in a new service, module, or microservice
- Replacing ad-hoc `print()` / `console.log()` calls with structured logs
- Adding correlation / trace IDs for distributed request tracing
- Wiring log output to a central collector (ELK, Loki, CloudWatch, Azure Monitor)
- Reviewing code for sensitive data leaking through log statements
- Configuring log levels per environment (DEBUG locally, INFO/WARN in production)
- Writing tests that assert a code path produced the expected log entry

---

## Core Principles

### 1. One central entry point
Every module obtains a logger through the same factory. No direct handler configuration, no `logging.basicConfig()` scattered across files. The root configuration lives in one place — at application startup.

### 2. Structured output (JSON in production)
Human-readable text in development. Machine-parseable JSON in staging and production so log aggregators can index, filter, and alert on individual fields without regex.

### 3. Levels are contracts, not suggestions

| Level | Meaning | Who reads it |
|---|---|---|
| `DEBUG` | Fine-grained diagnostic detail — variable values, branch decisions, timing | Developer during active debugging |
| `INFO`  | Normal lifecycle events — service started, request received, job completed | Ops dashboard, audit trail |
| `WARN`  | Unexpected but handled situation — retry triggered, deprecated API called, config fallback used | On-call engineer (not paged, but noticed) |
| `ERROR` | Operation failed, requires attention — exception caught, external call failed, data corrupt | On-call engineer (paged / alerted) |

Never use `ERROR` for expected control flow. Never use `DEBUG` in a hot path without a guard.

### 4. Context travels with the log record
Attach `service`, `environment`, `version`, `request_id`, and `trace_id` to every record so a single log line tells the full story without cross-referencing other systems.

### 5. Security: never log sensitive data
Passwords, tokens, PII, credit card numbers, and API keys must never appear in logs — not even at DEBUG. Filter them at the call site, not after the fact.

### 6. Logs are append-only — do not mutate
Once emitted a log line cannot be changed. Corrections belong in a new log record, not an edit to an existing one.

---

## Log Level Selection Guide

```
DEBUG  – use when:
  • tracing execution through a complex algorithm
  • logging input/output of an internal function during investigation
  • timing sub-steps of a pipeline
  • inspecting intermediate ML tensor shapes or metric values
  GUARD: if logger.isEnabledFor(DEBUG): ...  ← avoid expensive string formatting in hot paths

INFO   – use when:
  • application / service started / stopped
  • job started or completed (with duration and key result)
  • user action succeeded (login, project created)
  • configuration loaded (without values — just keys)
  • periodic health check: "Worker alive, queue depth=42"

WARN   – use when:
  • retrying a failed operation (include attempt number and reason)
  • falling back to a default (e.g. missing config → using built-in default)
  • using a deprecated code path (with migration hint)
  • rate limit approaching threshold
  • optional dependency unavailable (feature degraded, not broken)

ERROR  – use when:
  • an exception is caught and the operation cannot recover
  • an external service call failed after all retries
  • data is in an unexpected / corrupt state that blocks processing
  • a background job failed
  ALWAYS include: exception type, message, stack trace, affected entity id
```

---

## Logger Interface — Language-Agnostic Contract

Every application exposes a logger factory with this interface:

```
get_logger(name: str) -> Logger

Logger:
  debug(message, **context)
  info(message, **context)
  warn(message, **context)
  error(message, error=None, **context)
  with_context(**fields) -> Logger        # returns child logger pre-loaded with fields
```

---

## Python Implementation

### File layout

```
src/
  neuroedge_utils/
    logger.py           ← central factory and formatter
  neuroedge_settings/
    config.json         ← log_level, log_format ("text" | "json")
```

### Core logger module

```python
# src/neuroedge_utils/logger.py
"""
Centralised logger factory for all NeuroEdge modules.

Usage:
    from neuroedge_utils.logger import get_logger
    log = get_logger(__name__)
    log.info("Model loaded", model="yolov8n", platform="cpu", duration_ms=320)
    log.error("Inference failed", error=exc, use_case_id="ppe-001")
"""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from typing import Any


# ── Constants ────────────────────────────────────────────────────────────────

_LOG_LEVEL_ENV = "LOG_LEVEL"          # DEBUG | INFO | WARN | ERROR
_LOG_FORMAT_ENV = "LOG_FORMAT"        # text | json
_SERVICE_NAME = os.getenv("SERVICE_NAME", "neuroedge")
_ENVIRONMENT = os.getenv("APP_ENV", "development")
_APP_VERSION = os.getenv("APP_VERSION", "unknown")

_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO":  logging.INFO,
    "WARN":  logging.WARNING,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

_configured = False


# ── JSON formatter ────────────────────────────────────────────────────────────

class _JSONFormatter(logging.Formatter):
    """Emit one JSON object per line — compatible with ELK, Loki, CloudWatch."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level":     record.levelname,
            "logger":    record.name,
            "message":   record.getMessage(),
            "service":   _SERVICE_NAME,
            "env":       _ENVIRONMENT,
            "version":   _APP_VERSION,
        }

        # Extra fields attached via log.info("msg", extra={"key": val})
        _RESERVED = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "taskName",
        }
        for key, val in record.__dict__.items():
            if key not in _RESERVED:
                entry[key] = val

        # Exception details
        if record.exc_info:
            exc_type, exc_value, exc_tb = record.exc_info
            entry["error"] = {
                "type":    exc_type.__name__ if exc_type else None,
                "message": str(exc_value),
                "trace":   traceback.format_exception(exc_type, exc_value, exc_tb),
            }

        return json.dumps(entry, default=str)


# ── Text formatter ────────────────────────────────────────────────────────────

class _TextFormatter(logging.Formatter):
    """Human-readable coloured output for local development."""

    _COLOURS = {
        "DEBUG": "\033[36m",   # cyan
        "INFO":  "\033[32m",   # green
        "WARNING": "\033[33m", # yellow
        "ERROR": "\033[31m",   # red
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        colour = self._COLOURS.get(record.levelname, "")
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%H:%M:%S.%f")[:-3]
        base = f"{ts}  {colour}{record.levelname:<5}{self._RESET}  {record.name} — {record.getMessage()}"

        # Append extra context fields
        _RESERVED = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "taskName",
        }
        extras = {k: v for k, v in record.__dict__.items() if k not in _RESERVED}
        if extras:
            base += "  " + "  ".join(f"{k}={v!r}" for k, v in extras.items())

        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


# ── Bootstrap ────────────────────────────────────────────────────────────────

def configure_logging(
    level: str | None = None,
    fmt: str | None = None,
    force: bool = False,
) -> None:
    """Configure the root logger once at application startup.

    Call this in main.py / cli entry point before any other imports.
    Subsequent calls are no-ops unless force=True.

    Args:
        level: Override log level ("DEBUG" | "INFO" | "WARN" | "ERROR").
               Falls back to LOG_LEVEL env var, then "INFO".
        fmt:   Override format ("text" | "json").
               Falls back to LOG_FORMAT env var.
               Defaults to "text" in development, "json" elsewhere.
        force: Re-configure even if already configured (useful in tests).
    """
    global _configured
    if _configured and not force:
        return

    resolved_level = level or os.getenv(_LOG_LEVEL_ENV, "INFO").upper()
    numeric_level = _LEVEL_MAP.get(resolved_level, logging.INFO)

    is_dev = _ENVIRONMENT in ("development", "local", "dev")
    resolved_fmt = fmt or os.getenv(_LOG_FORMAT_ENV, "text" if is_dev else "json")

    formatter: logging.Formatter = (
        _TextFormatter() if resolved_fmt == "text" else _JSONFormatter()
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)

    # Suppress noisy third-party loggers
    for noisy in ("urllib3", "httpx", "httpcore", "asyncio", "botocore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


# ── Public factory ────────────────────────────────────────────────────────────

def get_logger(name: str) -> "_ContextLogger":
    """Return a ContextLogger for *name*.

    Usage::

        from neuroedge_utils.logger import get_logger
        log = get_logger(__name__)
        log.info("Benchmark complete", model="yolov8n", fps=42.3, platform="cpu")
    """
    if not _configured:
        configure_logging()   # safe default if caller forgot bootstrap
    return _ContextLogger(logging.getLogger(name))


# ── Context-aware logger wrapper ─────────────────────────────────────────────

class _ContextLogger:
    """Thin wrapper that passes kwargs as `extra=` to the underlying Logger.

    Enables:
        log.info("Job done", job_id="abc", duration_ms=320)
    instead of the verbose stdlib:
        log.info("Job done", extra={"job_id": "abc", "duration_ms": 320})
    """

    def __init__(self, logger: logging.Logger, _ctx: dict[str, Any] | None = None):
        self._log = logger
        self._ctx = _ctx or {}

    # ── Core level methods ────────────────────────────────────────────────────

    def debug(self, message: str, **kwargs: Any) -> None:
        if self._log.isEnabledFor(logging.DEBUG):
            self._log.debug(message, extra={**self._ctx, **kwargs})

    def info(self, message: str, **kwargs: Any) -> None:
        self._log.info(message, extra={**self._ctx, **kwargs})

    def warn(self, message: str, **kwargs: Any) -> None:
        self._log.warning(message, extra={**self._ctx, **kwargs})

    def error(
        self,
        message: str,
        error: BaseException | None = None,
        **kwargs: Any,
    ) -> None:
        self._log.error(
            message,
            exc_info=error or False,
            extra={**self._ctx, **kwargs},
        )

    # ── Context binding ───────────────────────────────────────────────────────

    def with_context(self, **fields: Any) -> "_ContextLogger":
        """Return a child logger pre-loaded with *fields* in every record.

        Use for request-scoped or job-scoped logging::

            request_log = log.with_context(request_id=req_id, user_id=user_id)
            request_log.info("Use case created", use_case_id="ppe-001")
            # → {... "request_id": "abc-123", "user_id": "u-456", "use_case_id": "ppe-001"}
        """
        return _ContextLogger(self._log, {**self._ctx, **fields})

    # ── Timing helper ─────────────────────────────────────────────────────────

    def timed(self, operation: str):
        """Context manager that logs duration at INFO on exit.

        Usage::

            with log.timed("model_export"):
                export_model(...)
            # → INFO  "model_export complete"  duration_ms=342
        """
        from contextlib import contextmanager
        import time

        @contextmanager
        def _timed():
            start = time.perf_counter()
            try:
                yield
            except Exception as exc:
                elapsed = int((time.perf_counter() - start) * 1000)
                self.error(f"{operation} failed", error=exc, duration_ms=elapsed)
                raise
            else:
                elapsed = int((time.perf_counter() - start) * 1000)
                self.info(f"{operation} complete", duration_ms=elapsed)

        return _timed()

    # ── stdlib passthrough ────────────────────────────────────────────────────

    def isEnabledFor(self, level: int) -> bool:
        return self._log.isEnabledFor(level)
```

### Bootstrap at startup

```python
# src/neuroedge_web_portal/backend/main.py  (or any CLI entry point)
from neuroedge_utils.logger import configure_logging

configure_logging()   # reads LOG_LEVEL and LOG_FORMAT from environment
```

### Module-level usage

```python
# src/neuroedge_model_profiler/backends/onnx_backend.py
from neuroedge_utils.logger import get_logger

log = get_logger(__name__)   # logger name = "neuroedge_model_profiler.backends.onnx_backend"


def run_benchmark(model: str, runs: int) -> BenchmarkResult:
    log.info("Benchmark starting", model=model, runs=runs)

    try:
        with log.timed("onnx_warmup"):
            _warmup(model)

        results = []
        for i in range(runs):
            log.debug("Run iteration", iteration=i, model=model)
            results.append(_infer(model))

        log.info("Benchmark complete", model=model, mean_ms=_mean(results), p95_ms=_p95(results))
        return BenchmarkResult(results)

    except OnnxRuntimeError as exc:
        log.error("ONNX inference failed", error=exc, model=model, runs=runs)
        raise


# Request-scoped child logger
def handle_request(request_id: str, use_case_id: str) -> None:
    rlog = log.with_context(request_id=request_id, use_case_id=use_case_id)
    rlog.info("Request received")
    # every subsequent log carries request_id and use_case_id automatically
    rlog.info("Processing complete", stage="benchmarking")
```

### FastAPI middleware integration

```python
# Attach correlation ID to every request log
import uuid
from fastapi import Request

@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    rlog = get_logger("neuroedge.portal").with_context(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )
    rlog.info("Request started")
    try:
        response = await call_next(request)
        rlog.info("Request completed", status=response.status_code)
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception as exc:
        rlog.error("Request failed", error=exc)
        raise
```

### Environment configuration

```ini
# .env
LOG_LEVEL=INFO          # DEBUG | INFO | WARN | ERROR
LOG_FORMAT=json         # text (dev) | json (production)
SERVICE_NAME=neuroedge-portal
APP_ENV=production
APP_VERSION=1.2.0
```

---

## TypeScript / Node.js Implementation

### Installation

```bash
npm install winston winston-daily-rotate-file
```

### Logger module

```typescript
// src/logger.ts
import winston from 'winston'

const { combine, timestamp, json, colorize, printf, errors } = winston.format

const SERVICE = process.env.SERVICE_NAME ?? 'neuroedge-portal'
const ENV     = process.env.APP_ENV       ?? 'development'
const VERSION = process.env.APP_VERSION   ?? 'unknown'
const LEVEL   = (process.env.LOG_LEVEL    ?? 'info').toLowerCase()

// ── Formatters ────────────────────────────────────────────────────────────────

const textFormat = combine(
  colorize({ all: true }),
  timestamp({ format: 'HH:mm:ss.SSS' }),
  errors({ stack: true }),
  printf(({ timestamp, level, message, stack, ...meta }) => {
    const extras = Object.keys(meta).length
      ? '  ' + Object.entries(meta).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join('  ')
      : ''
    return `${timestamp}  ${level.padEnd(7)}  ${message}${extras}${stack ? '\n' + stack : ''}`
  }),
)

const jsonFormat = combine(
  timestamp(),
  errors({ stack: true }),
  json(),
)

// ── Root logger ───────────────────────────────────────────────────────────────

const rootLogger = winston.createLogger({
  level: LEVEL,
  defaultMeta: { service: SERVICE, env: ENV, version: VERSION },
  format: ENV === 'development' ? textFormat : jsonFormat,
  transports: [new winston.transports.Console()],
  exitOnError: false,
})

// ── Factory ───────────────────────────────────────────────────────────────────

export function getLogger(module: string) {
  return rootLogger.child({ logger: module })
}

// ── Typed helper to guard DEBUG cost ─────────────────────────────────────────

export function isDebugEnabled(): boolean {
  return rootLogger.isLevelEnabled('debug')
}
```

### Usage in a service

```typescript
import { getLogger } from '../logger'

const log = getLogger('use-case-service')

export async function createUseCase(payload: CreateUseCaseDto): Promise<UseCaseFull> {
  log.info('Creating use case', { name: payload.name, domain: payload.domain })

  try {
    const uc = await db.useCases.create(payload)
    log.info('Use case created', { id: uc.id, name: uc.name })
    return uc
  } catch (err) {
    log.error('Use case creation failed', {
      error: err instanceof Error ? err.message : String(err),
      stack: err instanceof Error ? err.stack : undefined,
      payload_name: payload.name,
    })
    throw err
  }
}
```

### Express middleware

```typescript
import { Request, Response, NextFunction } from 'express'
import { randomUUID } from 'crypto'
import { getLogger } from './logger'

const log = getLogger('http')

export function requestLogger(req: Request, res: Response, next: NextFunction) {
  const requestId = (req.headers['x-request-id'] as string) ?? randomUUID()
  const reqLog = log.child({ request_id: requestId, method: req.method, path: req.path })

  req.headers['x-request-id'] = requestId
  const start = Date.now()

  reqLog.info('Request started')

  res.on('finish', () => {
    const level = res.statusCode >= 500 ? 'error' : res.statusCode >= 400 ? 'warn' : 'info'
    reqLog[level]('Request completed', { status: res.statusCode, duration_ms: Date.now() - start })
  })

  next()
}
```

---

## Java / Spring Boot Implementation

### Dependency (`pom.xml`)

```xml
<!-- SLF4J + Logback are included by spring-boot-starter — no extra dependency needed -->
<!-- For JSON output add: -->
<dependency>
  <groupId>net.logstash.logback</groupId>
  <artifactId>logstash-logback-encoder</artifactId>
  <version>7.4</version>
</dependency>
```

### Logger factory

```java
// src/main/java/com/cognizant/neuroedge/logging/AppLogger.java
package com.cognizant.neuroedge.logging;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import java.util.Map;
import java.util.function.Supplier;

/**
 * Central logger factory.
 * Usage: AppLogger log = AppLogger.of(MyService.class);
 */
public final class AppLogger {

    private final Logger log;

    private AppLogger(Class<?> clazz) {
        this.log = LoggerFactory.getLogger(clazz);
    }

    public static AppLogger of(Class<?> clazz) {
        return new AppLogger(clazz);
    }

    // ── Log level methods ──────────────────────────────────────────────────────

    public void debug(String message, Object... kvPairs) {
        if (log.isDebugEnabled()) {
            withFields(kvPairs, () -> log.debug(message));
        }
    }

    public void info(String message, Object... kvPairs) {
        withFields(kvPairs, () -> log.info(message));
    }

    public void warn(String message, Object... kvPairs) {
        withFields(kvPairs, () -> log.warn(message));
    }

    public void error(String message, Throwable error, Object... kvPairs) {
        withFields(kvPairs, () -> log.error(message, error));
    }

    // ── Context binding ────────────────────────────────────────────────────────

    /**
     * Add fields to the MDC for the duration of the block.
     * Fields are removed when the block exits (even on exception).
     *
     * Usage:
     *   log.withContext(Map.of("request_id", reqId, "user_id", userId), () -> {
     *       log.info("Processing request");
     *       service.process();
     *   });
     */
    public void withContext(Map<String, String> fields, Runnable block) {
        fields.forEach(MDC::put);
        try {
            block.run();
        } finally {
            fields.keySet().forEach(MDC::remove);
        }
    }

    // ── Internal helper ────────────────────────────────────────────────────────

    private void withFields(Object[] kvPairs, Runnable log) {
        if (kvPairs == null || kvPairs.length == 0) {
            log.run();
            return;
        }
        // kvPairs = ["key1", val1, "key2", val2, ...]
        for (int i = 0; i + 1 < kvPairs.length; i += 2) {
            MDC.put(String.valueOf(kvPairs[i]), String.valueOf(kvPairs[i + 1]));
        }
        try {
            log.run();
        } finally {
            for (int i = 0; i < kvPairs.length; i += 2) {
                MDC.remove(String.valueOf(kvPairs[i]));
            }
        }
    }
}
```

### Usage

```java
@Service
public class UseCaseService {

    private static final AppLogger log = AppLogger.of(UseCaseService.class);

    public UseCaseFull createUseCase(CreateUseCaseDto dto) {
        log.info("Creating use case", "name", dto.getName(), "domain", dto.getDomain());
        try {
            UseCaseFull uc = repository.save(dto);
            log.info("Use case created", "id", uc.getId(), "name", uc.getName());
            return uc;
        } catch (DataAccessException ex) {
            log.error("Use case creation failed", ex, "name", dto.getName());
            throw ex;
        }
    }
}
```

### Logback configuration (`logback-spring.xml`)

```xml
<configuration>

  <!-- Development: human-readable text -->
  <springProfile name="local,dev">
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
      <encoder>
        <pattern>%d{HH:mm:ss.SSS} %highlight(%-5level) %logger{36} — %msg%n%ex</pattern>
      </encoder>
    </appender>
  </springProfile>

  <!-- Production: JSON (ELK / CloudWatch compatible) -->
  <springProfile name="production,staging">
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
      <encoder class="net.logstash.logback.encoder.LogstashEncoder">
        <customFields>{"service":"neuroedge-api","env":"${APP_ENV}"}</customFields>
      </encoder>
    </appender>
  </springProfile>

  <root level="${LOG_LEVEL:-INFO}">
    <appender-ref ref="CONSOLE"/>
  </root>

  <!-- Silence noisy third-party libs -->
  <logger name="org.hibernate.SQL" level="WARN"/>
  <logger name="com.zaxxer.hikari" level="WARN"/>

</configuration>
```

---

## Structured Log Record Format

Every log record — regardless of language — should produce this JSON shape in production:

```json
{
  "timestamp":  "2026-05-17T09:23:44.123Z",
  "level":      "INFO",
  "logger":     "neuroedge_model_profiler.backends.onnx_backend",
  "message":    "Benchmark complete",
  "service":    "neuroedge-portal",
  "env":        "production",
  "version":    "1.2.0",

  "request_id": "3f8a2b1c-44d5-4e9a-b123-abc123def456",
  "trace_id":   "7a9f2e1b3c4d5e6f",
  "user_id":    "usr_8f3a",

  "model":      "yolov8n",
  "platform":   "cpu",
  "duration_ms": 342,

  "error": {
    "type":    "OnnxRuntimeError",
    "message": "Session creation failed: mismatched input shape",
    "trace":   ["Traceback (most recent call last):", "  File ..."]
  }
}
```

| Field | Source | Required |
|---|---|---|
| `timestamp` | Logger (UTC ISO-8601) | Always |
| `level` | Logger | Always |
| `logger` | `__name__` / class name | Always |
| `message` | Call site | Always |
| `service` | Env var `SERVICE_NAME` | Always |
| `env` | Env var `APP_ENV` | Always |
| `version` | Env var `APP_VERSION` | Always |
| `request_id` | Middleware (UUID per request) | In web services |
| `trace_id` | Distributed tracing header | In distributed systems |
| `error.*` | Exception object | On ERROR level |
| Domain fields | Call site kwargs | As needed |

---

## Log Destination Configuration

### Local development (stdout)

Default. No extra configuration needed. Set `LOG_FORMAT=text` for colour output.

### File rotation

```python
# Python — add to configure_logging() when LOG_DEST=file
from logging.handlers import RotatingFileHandler

file_handler = RotatingFileHandler(
    filename=log_dir / "app.log",
    maxBytes=50 * 1024 * 1024,   # 50 MB
    backupCount=7,                # keep 7 rotations (~350 MB max)
    encoding="utf-8",
)
file_handler.setFormatter(_JSONFormatter())
root.addHandler(file_handler)
```

### Centralized collectors

| Stack | Method | Notes |
|---|---|---|
| **ELK / Elastic** | Filebeat tail → Logstash → Elasticsearch | JSON format required; use `logstash-logback-encoder` for Java |
| **Grafana Loki** | Promtail or Docker driver | Label with `service`, `env`; queries via LogQL |
| **AWS CloudWatch** | SDK / Lambda built-in / ECS log driver | Set `LOG_STREAM=ecs`; use `awslogs` Docker driver |
| **Azure Monitor** | App Insights SDK or OTel exporter | Add `opencensus-ext-azure` for Python |
| **Datadog** | DD Agent with log collection enabled | Add `ddtrace` auto-instrumentation for traces |

```yaml
# docker-compose: route to Loki via Docker driver
services:
  backend:
    logging:
      driver: loki
      options:
        loki-url: "http://loki:3100/loki/api/v1/push"
        loki-external-labels: "service=neuroedge-portal,env=production"
```

---

## Security: What Never to Log

```python
# PASS — safe
log.info("User authenticated", user_id=user["id"], username=user["username"])
log.info("Token issued", user_id=user["id"], token_type="bearer", expires_in=86400)
log.debug("Request headers", headers={k: v for k, v in headers.items()
          if k.lower() not in ("authorization", "cookie", "x-api-key")})

# FAIL — NEVER log these
log.info("Login", password=form.password)                  # password
log.debug("Token", token=jwt_token)                        # secret
log.info("Card charged", card_number=card)                 # PAN
log.debug("API call", headers={"Authorization": token})    # bearer token
log.info("User", ssn=user.ssn)                            # PII
```

### Sanitise helper

```python
_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "credit_card", "card_number", "cvv", "ssn",
    "access_token", "refresh_token", "private_key",
})

def sanitise(data: dict) -> dict:
    return {
        k: ("***" if k.lower() in _SENSITIVE_KEYS else v)
        for k, v in data.items()
    }

# Usage:
log.debug("Request payload", **sanitise(request_body))
```

---

## Performance: Avoiding Log Overhead

```python
# PASS — guard expensive formatting in hot paths
if log.isEnabledFor(logging.DEBUG):
    # Only evaluated when DEBUG is active
    log.debug("Tensor stats", shape=str(tensor.shape), mean=float(tensor.mean()))

# FAIL — always computed even when DEBUG is off
log.debug("Tensor stats", shape=str(tensor.shape), mean=float(tensor.mean()))

# PASS — lazy formatting (Python 3.12+)
log.debug("Tensor stats %s", tensor.shape)   # stdlib % formatting is deferred

# PASS — async handler for high-throughput services
from logging.handlers import QueueHandler, QueueListener
import queue

log_queue = queue.Queue(-1)
queue_handler = QueueHandler(log_queue)
queue_listener = QueueListener(log_queue, *root.handlers, respect_handler_level=True)
queue_listener.start()
# Call queue_listener.stop() on application shutdown
```

---

## Testing Your Logger

### Assert a code path emitted the expected log record

```python
# Python — using pytest + caplog fixture
import logging
from neuroedge_model_profiler.backends.onnx_backend import run_benchmark

def test_benchmark_logs_completion(caplog):
    with caplog.at_level(logging.INFO, logger="neuroedge_model_profiler"):
        run_benchmark("yolov8n", runs=2)

    records = [r for r in caplog.records if r.message.startswith("Benchmark complete")]
    assert len(records) == 1
    assert records[0].levelname == "INFO"

def test_benchmark_logs_error_on_failure(caplog):
    with caplog.at_level(logging.ERROR):
        with pytest.raises(OnnxRuntimeError):
            run_benchmark("nonexistent_model", runs=1)

    assert any("ONNX inference failed" in r.message for r in caplog.records)
```

```typescript
// TypeScript — spy on the logger
import { getLogger } from '../logger'

jest.mock('../logger', () => ({
  getLogger: jest.fn(() => ({
    info:  jest.fn(),
    warn:  jest.fn(),
    error: jest.fn(),
    debug: jest.fn(),
  })),
}))

it('logs use case creation at INFO', async () => {
  const log = getLogger('use-case-service')
  await createUseCase({ name: 'Test', domain: 'custom' })

  expect(log.info).toHaveBeenCalledWith(
    'Use case created',
    expect.objectContaining({ name: 'Test' }),
  )
})
```

---

## Anti-Patterns to Avoid

```python
# FAIL — print() has no level, no format, no routing
print(f"Processing {model}")

# FAIL — logging.basicConfig() called in module, not at startup
logging.basicConfig(level=logging.DEBUG)   # ← in library code

# FAIL — f-string always evaluated, even when level is disabled
log.debug(f"Loaded {len(records)} records")   # use: log.debug("Loaded %d records", len(records))

# FAIL — swallowing exceptions silently
try:
    do_work()
except Exception:
    pass   # ← no log, no re-raise — failure is invisible

# FAIL — logging inside a loop without guard
for item in millions_of_items:
    log.debug("Processing item", item_id=item.id)   # flood risk

# PASS — sample or cap inside loops
for i, item in enumerate(items):
    if i % 1000 == 0:
        log.debug("Processing progress", done=i, total=len(items))

# FAIL — logging the exception message twice (once manually, once via exc_info)
log.error(f"Failed: {exc}", error=exc)   # message + exc_info duplicate

# PASS
log.error("Operation failed", error=exc)   # exc_info=exc adds type+trace automatically
```

---

## Quick-Reference: Log Level Decision Tree

```
Did the operation complete successfully?
  ├─ YES → did it happen as part of normal, routine flow?
  │         ├─ YES + high-frequency (>1/s) → DEBUG
  │         └─ YES + lifecycle event or user action → INFO
  └─ NO  → is the system still functional?
            ├─ YES + handled, recovered, or degraded gracefully → WARN
            └─ NO  + operation failed, needs attention → ERROR
```

---

*Skill version: 1.0 | Domain: SDLC / Development | Author: NeuroEdge | Date: 2026-05-17*
