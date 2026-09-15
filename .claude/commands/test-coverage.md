# Test Coverage

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /test-coverage · Skills: tdd-workflow, verification-loop`
>
> Then read these skill files before executing:
> - `agentic-assets/skills/SDLC/testing/tdd-workflow.md`
> - `agentic-assets/skills/SDLC/testing/verification-loop.md`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Step 1: Detect Test Framework

| Indicator | Coverage Command |
|-----------|-----------------|
| `jest.config.*` or `package.json` jest | `npx jest --coverage --coverageReporters=json-summary` |
| `vitest.config.*` | `npx vitest run --coverage` |
| `pytest.ini` / `pyproject.toml` pytest | `pytest --cov=src --cov-report=json` |
| `Cargo.toml` | `cargo llvm-cov --json` |
| `pom.xml` with JaCoCo | `mvn test jacoco:report` |
| `go.mod` | `go test -coverprofile=coverage.out ./...` |
| `CMakeLists.txt` with GoogleTest/Catch2 + `ctest` (C/C++) | `cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug -DCMAKE_CXX_FLAGS="--coverage" -DCMAKE_C_FLAGS="--coverage" && cmake --build build && ctest --test-dir build --output-on-failure && gcovr --root . --json-summary-pretty -o coverage.json` |
| `*.sln` / `*.csproj` (C#/.NET) | `dotnet test --collect:"XPlat Code Coverage" --results-directory ./coverage` (Coverlet emits `coverage.cobertura.xml`; run ReportGenerator for a summary) |

**Report formats to parse in Step 2:** pytest/jest/cargo emit a JSON summary; C/C++ via `gcovr` emits `coverage.json` (`--json-summary`); C#/.NET via Coverlet emits `coverage.cobertura.xml` (parse the `line-rate`/`branch-rate` attributes, or run ReportGenerator for a text summary). For C/C++ and .NET the tool must be present first (`gcovr`/`lcov`; `coverlet.collector` + `dotnet-reportgenerator-globaltool`) — if missing, report the gap instead of silently skipping.

## Step 2: Analyze Coverage Report

1. Run the coverage command
2. Parse the output (JSON summary or terminal output)
3. List files **below 80% coverage**, sorted worst-first
4. For each under-covered file, identify:
   - Untested functions or methods
   - Missing branch coverage (if/else, switch, error paths)
   - Dead code that inflates the denominator

## Step 3: Generate Missing Tests

For each under-covered file, generate tests following this priority:

1. **Happy path** — Core functionality with valid inputs
2. **Error handling** — Invalid inputs, missing data, network failures
3. **Edge cases** — Empty arrays, null/undefined, boundary values (0, -1, MAX_INT)
4. **Branch coverage** — Each if/else, switch case, ternary

### Test Generation Rules

- Place tests adjacent to source: `foo.ts` → `foo.test.ts` (or project convention)
- Use existing test patterns from the project (import style, assertion library, mocking approach)
- Mock external dependencies (database, APIs, file system)
- Each test should be independent — no shared mutable state between tests
- Name tests descriptively: `test_create_user_with_duplicate_email_returns_409`

## Step 4: Verify

1. Run the full test suite — all tests must pass
2. Re-run coverage — verify improvement
3. If still below 80%, repeat Step 3 for remaining gaps

## Step 5: Report

Show before/after comparison:

```
Coverage Report
──────────────────────────────
File                   Before  After
src/services/auth.ts   45%     88%
src/utils/validation.ts 32%    82%
──────────────────────────────
Overall:               67%     84%  PASS:
```

## Focus Areas

- Functions with complex branching (high cyclomatic complexity)
- Error handlers and catch blocks
- Utility functions used across the codebase
- API endpoint handlers (request → response flow)
- Edge cases: null, undefined, empty string, empty array, zero, negative numbers
