"""Repo-level guard tests for graph.json.

These assert the four behavioural requirements the demo depends on, and — more
importantly — that ``graph.json`` agrees with the *actual* Python imports in
``src/`` and with ``.circleci/test-suites.yml``. A declared DAG that has
drifted from the real one silently breaks test selection, so the imports are
checked by parsing the source rather than by trusting the JSON.

This suite is run from the repo root and is not one of the Smarter Testing
suites; it has no impact-key. It runs in the selector setup job.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from dag_select import Graph, GraphError, _match

REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_SUITES = REPO_ROOT / ".circleci" / "test-suites.yml"

#: Python top-level package name -> graph.json node id.
PACKAGE_TO_NODE = {
    "shared_core": "shared-core",
    "api": "api",
    "worker": "worker",
    "web": "web",
}


@pytest.fixture(scope="module")
def graph() -> Graph:
    return Graph.load(REPO_ROOT / "graph.json")


@pytest.fixture(scope="module")
def suites() -> dict:
    """Every suite document in .circleci/test-suites.yml, keyed by name."""
    with open(TEST_SUITES, "r", encoding="utf-8") as handle:
        documents = [d for d in yaml.safe_load_all(handle) if d]
    by_name = {}
    for document in documents:
        assert document["name"] not in by_name, "duplicate suite name"
        by_name[document["name"]] = document
    return by_name


# ---------------------------------------------------------------- structure


def test_graph_is_valid_and_acyclic(graph):
    assert set(graph.nodes) == {"shared-core", "api", "worker", "web"}
    assert graph.data["default_branch"] == "main"


def test_declared_dag_is_exactly_what_the_demo_needs(graph):
    declared = {n: sorted(graph.nodes[n].get("depends_on", [])) for n in graph.nodes}
    assert declared == {
        "shared-core": [],
        "api": ["shared-core"],
        "worker": ["api", "shared-core"],
        "web": ["api"],
    }


def test_every_node_root_exists_with_the_expected_layout(graph):
    for node_id, node in graph.nodes.items():
        root = REPO_ROOT / node["root"]
        assert root.is_dir(), "{0}: missing root {1}".format(node_id, node["root"])
        for expected in ("src", "tests"):
            assert (root / expected).is_dir(), "{0}: missing {1}/".format(node_id, expected)
        for expected in ("requirements.txt", "pytest.ini", "conftest.py", ".coveragerc"):
            assert (root / expected).is_file(), "{0}: missing {1}".format(node_id, expected)
        assert node["test_suite"]["working_directory"] == node["root"]


def test_there_is_exactly_one_test_suites_file_and_it_is_at_the_repo_root():
    """A per-subpackage test-suites.yml makes the subpackage the project
    directory, and the LCOV analysis data then references files outside it
    (``../../packages/shared-core/...``), which `circleci testsuite doctor`
    rejects. The single root file is load-bearing, not a style choice.
    """
    found = [
        p
        for p in REPO_ROOT.rglob(".circleci/test-suites.yml")
        if ".venv" not in p.parts
    ]
    assert found == [TEST_SUITES], "unexpected test-suites.yml locations: {0}".format(found)


def test_every_node_maps_to_a_suite_in_the_root_config(graph, suites):
    for node_id, node in graph.nodes.items():
        declared = node["test_suite"]
        assert declared["config"] == ".circleci/test-suites.yml"
        assert declared["name"] in suites, "{0}: no suite named {1!r}".format(
            node_id, declared["name"]
        )


def test_impact_keys_are_unique_and_agree_with_the_suite_file(graph, suites):
    keys = []
    for node_id, node in graph.nodes.items():
        declared = node["test_suite"]
        actual = suites[declared["name"]]["options"]["impact-key"]
        assert actual == declared["impact_key"], node_id
        keys.append(actual)
    assert len(keys) == len(set(keys)), "duplicate impact-key: {0}".format(sorted(keys))


def test_every_suite_enables_impact_analysis_and_dynamic_splitting(suites):
    for name, suite in suites.items():
        assert suite["options"]["test-impact-analysis"] is True, name
        assert suite["options"]["dynamic-test-splitting"] is True, name


def test_suite_commands_never_change_directory(suites):
    """The CLI runs discover/run/analysis from the CWD; `cd` and --directory
    inside them are explicitly unsupported.
    """
    for name, suite in suites.items():
        for key in ("discover", "run", "analysis"):
            command = suite[key]
            assert "cd " not in command, "{0}.{1} uses cd".format(name, key)
            assert "--directory" not in command, "{0}.{1} uses --directory".format(name, key)
        assert "<< outputs.junit >>" in suite["run"], name
        assert "<< test.atoms >>" in suite["run"], name
        assert "<< outputs.lcov >>" in suite["analysis"], name
        # discover must list files, not run anything
        assert suite["discover"].startswith("find tests "), name


def test_each_service_has_at_least_four_test_atoms(graph):
    for node_id, node in graph.nodes.items():
        atoms = sorted((REPO_ROOT / node["root"] / "tests").glob("test_*.py"))
        assert len(atoms) >= 4, "{0} has only {1} test atoms".format(node_id, len(atoms))


def test_requirements_and_circleci_are_full_test_run_paths(graph, suites):
    """Behavioural requirement: dependency and CI-config changes bypass
    selection and force a full run of that suite.
    """
    for node_id, node in graph.nodes.items():
        suite = suites[node["test_suite"]["name"]]
        listed = suite["options"]["full-test-run-paths"]
        # full-test-run-paths are matched against repo-root-relative changed files
        assert "{0}/requirements.txt".format(node["root"]) in listed, node_id
        assert ".circleci/*.yml" in listed, node_id


def test_test_selection_rules_reference_real_test_atoms(graph, suites):
    for node_id, node in graph.nodes.items():
        suite = suites[node["test_suite"]["name"]]
        for rule in suite["options"].get("test-selection-rules", []):
            atom = REPO_ROOT / node["root"] / rule["test-atom"]
            assert atom.is_file(), "{0}: rule points at missing {1}".format(
                node_id, rule["test-atom"]
            )


# ------------------------------------------------- declared vs real imports


def _foreign_imports(src_root: Path, own_package: str) -> set:
    """Top-level in-repo packages imported by any module under ``src_root``."""
    found = set()
    for source_file in sorted(src_root.rglob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"), str(source_file))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if top in PACKAGE_TO_NODE and top != own_package:
                    found.add(PACKAGE_TO_NODE[top])
    return found


@pytest.mark.parametrize(
    "node_id,package",
    [("shared-core", "shared_core"), ("api", "api"), ("worker", "worker"), ("web", "web")],
)
def test_real_imports_match_declared_dependencies(graph, node_id, package):
    src_root = REPO_ROOT / graph.nodes[node_id]["root"] / "src"
    actual = _foreign_imports(src_root, package)
    declared = set(graph.nodes[node_id].get("depends_on", []))
    assert actual == declared, (
        "{0}: source imports {1} but graph.json declares {2}".format(
            node_id, sorted(actual), sorted(declared)
        )
    )


def test_web_reaches_shared_core_only_through_api(graph):
    """web must not import shared_core directly — the edge is transitive."""
    src_root = REPO_ROOT / graph.nodes["web"]["root"] / "src"
    assert _foreign_imports(src_root, "web") == {"api"}
    assert "shared-core" in graph.transitive_dependencies("web")


def _import_in_subprocess(statement: str, *src_roots: Path):
    return subprocess.run(
        [sys.executable, "-c", statement],
        cwd=str(REPO_ROOT),
        env={
            "PYTHONPATH": ":".join(str(p) for p in src_roots),
            "PATH": "/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        capture_output=True,
        text=True,
    )


WORKER_SRC = REPO_ROOT / "services" / "worker" / "src"
WEB_SRC = REPO_ROOT / "services" / "web" / "src"
API_SRC = REPO_ROOT / "services" / "api" / "src"
SHARED_SRC = REPO_ROOT / "packages" / "shared-core" / "src"


@pytest.mark.parametrize(
    "statement,src_roots,missing",
    [
        # worker -> api is a hard import, not just a graph.json declaration
        ("import worker.jobs", (WORKER_SRC, SHARED_SRC), "api"),
        # web -> api likewise
        ("import web.views", (WEB_SRC, SHARED_SRC), "api"),
        # api -> shared_core likewise
        ("import api.pricing", (API_SRC,), "shared_core"),
    ],
)
def test_dependencies_are_real_imports_not_just_declarations(statement, src_roots, missing):
    """Drop one dependency from sys.path and the dependent must fail to import.

    This is the proof that the DAG in graph.json describes the code rather
    than merely asserting something about it.
    """
    result = _import_in_subprocess(statement, *src_roots)
    assert result.returncode != 0, "expected {0!r} to fail without {1}".format(
        statement, missing
    )
    assert "ModuleNotFoundError" in result.stderr
    assert repr(missing) in result.stderr


def test_the_same_imports_succeed_once_every_dependency_is_present():
    """Control for the test above: the failures are about the missing
    dependency, not about broken code.
    """
    for statement, src_roots in [
        ("import worker.jobs", (WORKER_SRC, API_SRC, SHARED_SRC)),
        ("import web.views", (WEB_SRC, API_SRC, SHARED_SRC)),
        ("import api.pricing", (API_SRC, SHARED_SRC)),
    ]:
        result = _import_in_subprocess(statement, *src_roots)
        assert result.returncode == 0, "{0} failed: {1}".format(statement, result.stderr)


def test_package_inits_do_not_re_export_submodules():
    """An eager ``__init__`` gives every test atom in a package the same
    coverage footprint, which collapses test impact analysis to "run
    everything". ``circleci testsuite doctor`` reports this as "Every test
    atom impacted the same files."
    """
    inits = [
        SHARED_SRC / "shared_core" / "__init__.py",
        API_SRC / "api" / "__init__.py",
        WORKER_SRC / "worker" / "__init__.py",
        WEB_SRC / "web" / "__init__.py",
    ]
    for init in inits:
        tree = ast.parse(init.read_text(encoding="utf-8"), str(init))
        imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
        assert imports == [], "{0} must not import anything, found {1}".format(
            init.relative_to(REPO_ROOT), len(imports)
        )


# ------------------------------------------------------ behavioural require


def test_changing_shared_core_selects_all_three_services(graph):
    decision = graph.select(["packages/shared-core/src/shared_core/money.py"])
    assert decision["selected"] == ["api", "shared-core", "web", "worker"]
    assert decision["full_run"] is False
    assert decision["reasons"]["web"] == "depends on shared-core"


def test_changing_api_src_selects_api_worker_and_web(graph):
    decision = graph.select(["services/api/src/api/pricing.py"])
    assert decision["selected"] == ["api", "web", "worker"]
    assert "shared-core" not in decision["selected"]
    assert decision["reasons"]["worker"] == "depends on api"


def test_changing_only_web_src_selects_only_web(graph):
    decision = graph.select(["services/web/src/web/routing.py"])
    assert decision["selected"] == ["web"]


def test_changing_only_worker_src_selects_only_worker(graph):
    decision = graph.select(["services/worker/src/worker/queue.py"])
    assert decision["selected"] == ["worker"]


def test_service_requirements_changes_select_that_services_lane(graph):
    assert graph.select(["services/web/requirements.txt"])["selected"] == ["web"]
    assert graph.select(["services/api/requirements.txt"])["selected"] == [
        "api",
        "web",
        "worker",
    ]


@pytest.mark.parametrize(
    "path",
    [
        "graph.json",
        ".circleci/test-suites.yml",
        ".circleci/config.yml",
        "tools/dag_select.py",
        "tests/test_graph_dag.py",
        "requirements-dev.txt",
    ],
)
def test_repo_wide_paths_force_a_full_run(graph, path):
    decision = graph.select([path])
    assert decision["full_run"] is True
    assert decision["selected"] == ["api", "shared-core", "web", "worker"]


def test_unattributed_paths_select_nothing(graph):
    decision = graph.select(["README.md", "docs/notes.md"])
    assert decision["selected"] == []
    assert decision["unattributed_paths"] == ["README.md", "docs/notes.md"]


def test_multiple_changes_union_their_selections(graph):
    decision = graph.select(
        ["services/web/src/web/routing.py", "services/worker/src/worker/queue.py"]
    )
    assert decision["selected"] == ["web", "worker"]


def test_no_changes_selects_nothing(graph):
    assert graph.select([])["selected"] == []


# ----------------------------------------------------------- glob semantics


@pytest.mark.parametrize(
    "path,pattern,expected",
    [
        ("services/api/src/api/pricing.py", "services/api/**", True),
        ("services/apix/src/main.py", "services/api/**", False),
        ("services/api/requirements.txt", "services/api/**", True),
        (".circleci/config.yml", ".circleci/**", True),
        ("a/b/c.yml", "a/*.yml", False),
        ("a/c.yml", "a/*.yml", True),
    ],
)
def test_glob_semantics(path, pattern, expected):
    assert _match(path, pattern) is expected


def test_graph_rejects_a_bad_schema():
    with pytest.raises(GraphError):
        Graph({"schema": "nope", "nodes": []})


def test_graph_rejects_unknown_dependencies():
    with pytest.raises(GraphError):
        Graph(
            {
                "schema": "ssp.dag/v1",
                "nodes": [{"id": "a", "paths": [], "depends_on": ["ghost"]}],
            }
        )


def test_graph_rejects_cycles():
    with pytest.raises(GraphError):
        Graph(
            {
                "schema": "ssp.dag/v1",
                "nodes": [
                    {"id": "a", "paths": [], "depends_on": ["b"]},
                    {"id": "b", "paths": [], "depends_on": ["a"]},
                ],
            }
        )


def test_graph_json_is_stable_json():
    raw = (REPO_ROOT / "graph.json").read_text(encoding="utf-8")
    assert json.loads(raw)["schema"] == "ssp.dag/v1"
    assert raw.endswith("\n")
