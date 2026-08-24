# ssp-platform-monorepo

A Python monorepo with a **real** dependency DAG, built to drive two CircleCI
capabilities in the SugarSnapPeas demo:

1. **Dynamically generated job graphs** — the `sugarsnappeas/selector` orb reads
   [`graph.json`](graph.json), diffs the branch against its merge base, walks the DAG, and
   emits one pipeline lane per impacted build unit.
2. **Smarter Testing (test impact analysis + dynamic test splitting)** — inside each selected
   lane, `circleci testsuite run` picks only the test atoms whose coverage footprint intersects
   the change.

The two layers are independent and they compose: the DAG decides *which services build*, impact
analysis decides *which tests run inside each one*.

---

## Layout

```
.circleci/test-suites.yml      all four Smarter Testing suites (see "Why one file" below)
graph.json                     the dependency DAG
tools/dag_select.py            reference implementation of the graph.json selection algorithm
tests/test_graph_dag.py        guard suite: graph.json vs. the real imports and the suite config
requirements-dev.txt           tooling for the repo-root guard suite only

packages/shared-core/          library  — money, validation, retry, ids
services/api/                  service  — catalog, pricing, orders, errors
services/worker/               service  — queue, jobs, settlement, reporting
services/web/                  service  — routing, templating, views, app
```

Every build unit has the same shape: `src/`, `tests/test_*.py`, `requirements.txt`,
`pytest.ini`, `conftest.py`, `.coveragerc`.

---

## The dependency DAG

```
                 shared-core
                  ^   ^
                  |    \
                  |     \
                 api     \
                ^   ^     \
               /     \     \
             web    worker--+
```

| Build unit | Depends on (direct) | Reaches transitively |
|---|---|---|
| `shared-core` | — | — |
| `api` | `shared-core` | — |
| `worker` | `shared-core`, `api` | — |
| `web` | `api` | `shared-core` (through `api`) |

The DAG is **non-uniform on purpose** — `web` does not import `shared_core` directly, so a
shared-core change reaches it via a two-hop path. That makes the selector's traversal log
worth showing.

These are genuine Python imports, not declarations.
`tests/test_graph_dag.py::test_dependencies_are_real_imports_not_just_declarations`
drops each dependency from `sys.path` in a subprocess and asserts the dependent fails with
`ModuleNotFoundError`, and
`test_real_imports_match_declared_dependencies` parses every module with `ast` and asserts the
import graph equals the `depends_on` lists in `graph.json`. If the two ever drift, the guard
suite fails.

---

## `graph.json` schema (`ssp.dag/v1`)

The contract between this repo and `analyse.py` in the `sugarsnappeas/selector` orb.
[`tools/dag_select.py`](tools/dag_select.py) is the executable reference implementation.

### Top level

| Key | Type | Meaning |
|---|---|---|
| `schema` | string | Always `"ssp.dag/v1"`. Consumers must reject anything else. |
| `description` | string | Free text. |
| `default_branch` | string | Branch the merge base is computed against. |
| `selection` | object | Prose description of the algorithm below; self-documenting, not machine-read. |
| `full_run_paths` | list of globs | A change to any of these selects **every** node. |
| `nodes` | list of node | The build units. |

### Node

| Key | Type | Meaning |
|---|---|---|
| `id` | string | Unique node identifier; used as the lane name. |
| `kind` | `"library"` \| `"service"` | Lets the selector treat libraries differently if it wants to. |
| `root` | path | Directory the node lives in. |
| `paths` | list of globs | A changed file matching any of these marks the node **directly changed**. |
| `depends_on` | list of node ids | Direct dependencies. Must be acyclic and must name existing nodes. |
| `test_suite.config` | path | Where the Smarter Testing config lives. |
| `test_suite.name` | string | The suite name to pass to `circleci testsuite run`. |
| `test_suite.impact_key` | string | Must be unique across nodes. |
| `test_suite.working_directory` | path | Directory to run `circleci testsuite` from. Equals `root`. |

### Selection algorithm

Given a set of changed file paths, all **relative to the repo root**:

1. If any changed path matches a glob in top-level `full_run_paths` → **select every node**, stop.
2. Otherwise, for each changed path, select every node with a matching glob in its `paths`.
   These are the *directly changed* nodes. A path matching no node is *unattributed* and
   selects nothing (the selector should log it).
3. Take the **reverse-transitive closure** over `depends_on`: if node `X` is selected and node
   `Y` lists `X` in `Y.depends_on`, select `Y`, recursively.

Glob semantics: `*` matches within one path segment, `**` matches across segments.

Emit one lane per selected node. `depends_on` describes *impact*, not build ordering — lanes
may run in parallel.

```console
$ python tools/dag_select.py packages/shared-core/src/shared_core/money.py
api             depends on shared-core
shared-core     changed: packages/shared-core/src/shared_core/money.py
web             depends on shared-core
worker          depends on shared-core

$ git diff --name-only origin/main... | python tools/dag_select.py - --json
```

---

## Smarter Testing

### Why one `test-suites.yml` at the repo root

Each suite is still **run from its own subpackage**, and no `discover` / `run` / `analysis`
command uses `cd` or `--directory`:

```console
$ cd services/api && circleci testsuite run "api tests"
```

The CLI walks *up* the tree to find `.circleci/test-suites.yml`, and the directory it finds it
in becomes the **project directory** for coverage.

The file **cannot** live in `services/<name>/.circleci/`. With it there, the project directory
is the service, and the LCOV data references `../../packages/shared-core/...`, which escapes it.
`circleci testsuite doctor` fails with *"Analysis command could not locate covered files in the
project directory"* and instructs you to move the file to the project root. Those cross-package
coverage edges are the whole point of the monorepo demo, so the root is the only workable
location.

### Two other things the doctor caught

Both are load-bearing; neither is obvious from the reference docs.

1. **`junit_family = xunit1` in every `pytest.ini`.** pytest's default `xunit2` output omits the
   `file` attribute on `<testcase>`. Without it the CLI cannot map a JUnit result back to the
   atom that produced it, and reports
   *"could not find JUnit XML result for test atoms: …"* — every atom is treated as failed.
2. **No re-exports in any package `__init__.py`.** An eager `__init__` means importing
   `api.errors` also loads `api.pricing`, `api.orders` and `api.catalog`, so every test atom
   ends up with an identical coverage footprint and selection degenerates to "run everything".
   The doctor calls this *"Every test atom impacted the same files."* Import submodules
   directly: `from api.pricing import quote`.

### Suites

| Suite name | Run from | `impact-key` | Atoms |
|---|---|---|---|
| `shared-core tests` | `packages/shared-core` | `monorepo-shared-core` | 4 |
| `api tests` | `services/api` | `monorepo-api` | 5 |
| `worker tests` | `services/worker` | `monorepo-worker` | 5 |
| `web tests` | `services/web` | `monorepo-web` | 5 |

Test atoms are **files**, discovered with `find` rather than `pytest --collect-only` — every
line of `discover` stdout is parsed as an atom, so a collector's banner lines would corrupt the
list.

`analysis` emits LCOV, which analyses one atom at a time and needs `coverage.py >= 6.3`.

### Coverage footprints

Each atom has a genuinely different footprint, which is what makes selection interesting.
Verified per atom with `coverage run -m pytest <atom> && coverage lcov`:

| Atom | shared-core | api | own service |
|---|---|---|---|
| `api/tests/test_errors.py` | — | `errors` | — |
| `api/tests/test_catalog.py` | `ids`, `money`, `validation` | `catalog`, `errors` | — |
| `api/tests/test_pricing.py` | `ids`, `money`, `validation` | `catalog`, `errors`, `pricing` | — |
| `worker/tests/test_queue.py` | — | — | `queue` |
| `worker/tests/test_reporting.py` | `ids`, `money` | — | `reporting` |
| `worker/tests/test_jobs.py` | `ids`, `money`, `retry`, `validation` | 4 modules | `jobs`, `queue` |
| `web/tests/test_routing.py` | — | — | `routing` |
| `web/tests/test_views.py` | `ids`, `money`, `validation` | `catalog`, `errors`, `pricing` | `templating`, `views` |

`test_errors.py`, `test_queue.py`, `test_routing.py` and `test_templating.py` are the **control
atoms**: they have no shared-core edge, so a shared-core change must *not* select them. That
contrast is the demo.

### `full-test-run-paths`

Per suite: that service's `requirements.txt`, `pytest.ini`, `.coveragerc`, `conftest.py`, and
`.circleci/*.yml`. Matched against repo-root-relative changed paths.

`packages/shared-core/**` is deliberately **not** listed. Coverage sees those edges for real, so
impact analysis can select the precise subset of atoms that touch shared-core. Listing it would
force a full run and throw that precision away — the DAG layer already guarantees all three
service lanes get built.

### `test-selection-rules`

Each service always runs its contract check (`test_api_smoke.py`, `test_worker_pipeline.py`,
`test_web_rendering.py`) via `include: true`. Coverage cannot express "this is the smoke test".

---

## Behavioural guarantees

Asserted in `tests/test_graph_dag.py`, at the DAG layer:

| Change | Lanes selected |
|---|---|
| `packages/shared-core/**` | `shared-core`, `api`, `worker`, `web` — all three services |
| `services/api/src/**` | `api`, `worker`, `web` — both dependents fan out |
| `services/web/src/**` | `web` only |
| `services/worker/src/**` | `worker` only |
| `services/<x>/requirements.txt` | `<x>` and its dependents (full run inside that lane) |
| `graph.json`, `.circleci/**`, `tools/**`, `tests/**` | everything |

> **Note on a conflict with `CONVENTIONS.md`.** That document's behavioural requirement 2 says a
> `services/api/src/**` change selects *only* `api`. That is not achievable with a truthful DAG:
> `worker` and `web` both import `api` in-process, so an api change genuinely can break them.
> This repo implements the honest fan-out (`api` → `api`, `worker`, `web`). Raised with the
> coordinator.

---

## Running the tests

```console
$ python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

# per build unit
$ cd packages/shared-core && pytest        # 75 passed
$ cd services/api         && pytest        # 58 passed
$ cd services/worker      && pytest        # 40 passed
$ cd services/web         && pytest        # 54 passed

# repo-root guard suite
$ pytest                                   # 45 passed

# Smarter Testing setup check, per suite
$ cd services/api && circleci testsuite --local doctor "api tests"
```

There are no third-party runtime dependencies anywhere — only `pytest` and `coverage` (plus
`PyYAML` for the repo-root guard suite). Cross-package imports are wired by each subpackage's
`conftest.py` putting the right `src/` directories on `sys.path`, deliberately avoiding a
packaging tool: the demo is about CI, not packaging, and it keeps every imported module a real
file inside the repository, which is what makes the coverage edges usable.

All tests are **in-process**. Nothing talks to another service over HTTP, because an HTTP call
produces no coverage edge and would make impact analysis silently under-select.

<!-- selection demo -->
