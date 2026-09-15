# LOC Count Command

## NeuroEdge Assets

> At the start of your response output exactly:
> `[ NeuroEdge Assets ]  /loc-count`
<!-- neuroedge-assets-patched source-version=426fa40 -->

## Usage

`/loc-count [Web|Device|All]`

Count and categorize source files across NeuroEdge projects.

## Arguments

`$ARGUMENTS`:
- `Web`    — count files in NeuroEdge-Web only
- `Device` — count files in NeuroEdge-Device only
- `All`    — count both projects and show side-by-side summary (default when no arg given)

## Execution

When this command runs, execute the following steps using Bash tool calls.

### Step 1 — Resolve target(s)

```
Web    → c:/SanjeevE/NeuroEdge Physical AI Studio/NeuroEdge-Web
Device → c:/SanjeevE/NeuroEdge Physical AI Studio/NeuroEdge-Device
All    → both of the above
```

### Step 2 — Run counts for each target project

For **NeuroEdge-Web**, run these Bash commands (all from the project root):

```bash
# Python source (src/ only, excl tests and __pycache__)
find src -name "*.py" ! -name "test_*.py" ! -path "*/tests/*" | wc -l

# Python tests
find src \( -name "test_*.py" -o -path "*/tests/test_*.py" \) | wc -l

# TypeScript / TSX source (excl node_modules)
find src \( -name "*.ts" -o -name "*.tsx" \) -not -path "*/node_modules/*" | wc -l

# Config: YAML / TOML (excl data/, node_modules, .venv, MagicMock)
find . \( -name "*.yaml" -o -name "*.yml" -o -name "*.toml" \) \
  -not -path "./.git/*" -not -path "./data/*" \
  -not -path "*/node_modules/*" -not -path "./.venv*/*" \
  -not -path "./MagicMock/*" | wc -l

# Config: JSON (project config only — excl data/, node_modules, .venv, MagicMock)
find . -name "*.json" \
  -not -path "./.git/*" -not -path "./data/*" \
  -not -path "*/node_modules/*" -not -path "./.venv*/*" \
  -not -path "./MagicMock/*" | wc -l

# Makefile
find . \( -name "Makefile" -o -name "*.mk" \) -not -path "./.git/*" | wc -l
```

For **NeuroEdge-Device**, run these Bash commands:

```bash
# Python source (excl tests, .venv, build, site-packages)
find . -name "*.py" ! -name "test_*.py" ! -path "*/tests/*" \
  -not -path "./.git/*" -not -path "./.venv/*" \
  -not -path "*/site-packages/*" -not -path "*/build/*" | wc -l

# Python tests
find . \( -name "test_*.py" -o -path "*/tests/test_*.py" \) \
  -not -path "./.git/*" -not -path "./.venv/*" \
  -not -path "*/site-packages/*" | wc -l

# C++ source (excl build/)
find . \( -name "*.cpp" -o -name "*.hpp" -o -name "*.h" \) \
  -not -path "./.git/*" -not -path "*/build/*" | wc -l

# Config: YAML / JSON / TOML (excl build, .venv, site-packages)
find . \( -name "*.yaml" -o -name "*.yml" -o -name "*.json" -o -name "*.toml" \) \
  -not -path "./.git/*" -not -path "*/build/*" \
  -not -path "./.venv/*" -not -path "*/site-packages/*" | wc -l

# Makefile
find . \( -name "Makefile" -o -name "*.mk" \) -not -path "./.git/*" | wc -l

# CMake
find . \( -name "CMakeLists.txt" -o -name "*.cmake" \) \
  -not -path "./.git/*" -not -path "*/build/*" | wc -l

# Dockerfile
find . -name "Dockerfile*" -not -path "./.git/*" | wc -l

# Shell scripts
find . -name "*.sh" -not -path "./.git/*" | wc -l
```

### Step 3 — Format output

Present the results as a markdown table per project:

**NeuroEdge-Web**

| Category | Type | Count |
|---|---|---|
| Code | Python source | N |
| Code | TypeScript / TSX | N |
| Test | Python tests | N |
| Config | YAML / TOML | N |
| Config | JSON (project) | N |
| Make | Makefile | N |

**NeuroEdge-Device**

| Category | Type | Count |
|---|---|---|
| Code | Python source | N |
| Code | C++ / HPP / H | N |
| Test | Python tests | N |
| Config | YAML / JSON / TOML | N |
| Make | Makefile | N |
| Make | CMake | N |
| Make | Dockerfile | N |
| Make | Shell scripts | N |

If `All`, also show a side-by-side summary table:

| Category | Web | Device |
|---|---|---|
| Python code | N | N |
| TypeScript | N | — |
| C++ | — | N |
| Tests | N | N |
| Config | N | N |
| Make / Build | N | N |
| **Total** | **N** | **N** |

### Step 4 — Flag anomalies

After the tables, check for and report any of the following:

- `MagicMock/` directory in Web root with JSON files → flag as leaked test artifacts to gitignore/delete
- Test file count is less than 20% of source file count → flag as low test coverage ratio
- Config file count exceeds source file count by 3x or more → note as data-heavy project
