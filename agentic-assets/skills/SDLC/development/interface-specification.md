---
name: interface-specification
description: Contract-first specification of every interface a component exposes or consumes — operations, request/response/error shapes, invariants, and versioning — defined at design time before code. The backbone of a Low-Level Design (LLD). Covers REST/OpenAPI, internal module/adapter Protocols, CLIs, and event/message contracts.
origin: NeuroEdge
---

# Interface Specification (contract-first)

Define the **contract before the code**. The contract is a shared, versioned artifact that drives
implementation, tests, and documentation at once — so breaking changes are caught at **design
time**, not in production. Contract-first (design-first) is the practice the OpenAPI Initiative and
most integration guidance recommend; teams that do it report materially faster integration and
fewer interface defects. An interface left to "whatever the code ends up doing" is a defect waiting
to happen.

This is the **backbone of the Low-Level Design (LLD)**: every boundary a component exposes or
consumes gets a spec here, precise enough that the implementer writes no new interface decisions.

## What "interface" means here (not just REST)

Specify **every** contract crossing a boundary, in the right notation:

| Interface kind | Specify with |
|---|---|
| REST / HTTP API | OpenAPI-style: path + verb, params, request/response schemas, status codes, errors, auth, pagination |
| Internal module / adapter (in-process) | The typed interface/`Protocol`: method signatures, argument & return **types**, the **error contract** (returns a result object vs raises — and which), and invariants |
| CLI / command | Subcommands, flags, argument types, exit codes, stdout/stderr contract |
| Event / message | Topic/queue, message schema, ordering/idempotency/at-least-once semantics, versioning |
| File / state artifact | On-disk schema (fields, types, required), validation rule, atomicity guarantee |

## What every interface spec must state

For each operation on the interface:

1. **Signature** — name, inputs (with types), output (with type). For code interfaces, the exact
   function/method signature the build will implement.
2. **Request / input schema** — fields, types, required vs optional, constraints, an example.
3. **Response / output schema** — success shape(s) + an example.
4. **Error contract** — the failure modes and how they surface. Be explicit about the discipline:
   *does this boundary raise, or return a typed result?* (e.g. AgentForge's adapter discipline:
   return an explicit result object, **never raise** on an external failure — mirror it, don't
   re-decide it.) Enumerate error codes/variants.
5. **Invariants & preconditions** — what must hold before/after (e.g. "authoritative state is
   never mutated by a projection write"; "a hard gate is never cleared through this path").
6. **Idempotency / ordering / concurrency** — at-most-once? safe to retry? atomic?
7. **Versioning** — how the contract evolves without breaking consumers (additive-only fields,
   deprecation path). State it even for internal interfaces (e.g. "the enum gains values
   additively; consumers must tolerate unknown values").

## Contract-first workflow

1. **Write the spec first** — before implementation, as part of the LLD.
2. **One source of truth** — product, callers, and implementers iterate on the same contract.
3. **Examples + mock early** — validate usability before code (for REST, a mock server; for a
   module, example call/return pairs in the LLD).
4. **Contract test in CI** — assert the implementation matches the spec, so specification drift is
   caught mechanically, not in review. Bind each interface to the TC-NN that verifies it.
5. **Detect breaking changes at design time** — a diff of the contract is the review surface.

## REST specifics (when the interface is HTTP)

- Resources are **nouns**, standard HTTP **verbs**; define request/response **schemas with
  examples**; specify **pagination, filtering, sorting, and the error shape early**.
- Prefer an **OpenAPI** document (YAML/JSON) as the machine-readable contract; generate server
  stubs / client SDKs and contract tests from it rather than hand-writing them.

## In an AgentForge LLD

Every module boundary in `neuroedge/docs/project_related/<objective-slug>/04-development/lld.md` carries an interface spec: the adapter `Protocol` (methods,
result types, never-raise error contract), the config surface, the CLI subcommands + exit codes,
and any on-disk artifact schema — each with invariants and the TC-NN that will contract-test it.
The LLD is complete when a developer can implement each interface from its spec **without inventing
a signature, an error mode, or an invariant.**

## Sources

- [OpenAPI — Best Practices](https://learn.openapis.org/best-practices.html) (design-first)
- [Contract-first API development (OpenAPI)](https://asoasis.tech/articles/2026-04-28-0253-api-contract-first-design-openapi/)
- [Gravitee — Contract-first API design principles](https://www.gravitee.io/blog/top-principles-api-design-robust-scalable-efficient-apis)
- [Why contract-first prevents integration failures](https://designgurus.substack.com/p/openapi-protobuf-and-graphql-how)
