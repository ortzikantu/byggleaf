"""Architecture guards for ByggLeaf.

These tests are intentionally structural rather than behavioural.  They fail
when a future change makes the package easier to write but harder to reason
about: an entry-layer import from core, a third-party package outside the
approved two, a cycle, JavaScript sneaking into the static assets, or missing
wheel package-data.
"""

from __future__ import annotations

import ast
import sys
import tomllib
import unittest
from pathlib import Path

from byggleaf.core.locales import canonicalize_language

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "byggleaf"
CORE = PACKAGE / "core"
ASSETS = PACKAGE / "assets"
TEMPLATES = PACKAGE / "templates"
LOCALES = PACKAGE / "locales"

APPROVED_THIRD_PARTY = {"markdown", "jinja2"}
ENTRY_MODULES = (
    "byggleaf.app",
    "byggleaf.cli",
)


def _python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_parts(path: Path) -> list[str]:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    is_package = bool(parts and parts[-1] == "__init__")
    if is_package:
        return parts[:-1]
    return parts[:-1]


def _imports(path: Path) -> set[str]:
    """Resolve imports to absolute module names (attributes are not modules)."""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_parts(path)
    result: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                result.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                if node.level > len(package):
                    continue
                base = package[: len(package) - (node.level - 1)]
                if node.module:
                    result.add(".".join(base + node.module.split(".")))
                else:
                    for alias in node.names:
                        if alias.name != "*":
                            result.add(".".join(base + [alias.name]))
            elif node.module:
                result.add(node.module)

    return result


def _is_within(module: str, target: str) -> bool:
    return module == target or module.startswith(target + ".")


def _import_graph() -> dict[str, set[str]]:
    modules = {_module_name(path): path for path in _python_files(PACKAGE)}
    graph: dict[str, set[str]] = {name: set() for name in modules}
    for name, path in modules.items():
        for imported in _imports(path):
            if imported in modules:
                graph[name].add(imported)
    return graph


class DependencyDirectionTests(unittest.TestCase):
    def test_core_never_imports_outer_layers(self) -> None:
        for path in _python_files(CORE):
            for module in _imports(path):
                for forbidden in ENTRY_MODULES:
                    with self.subTest(file=path.name, imported=module):
                        self.assertFalse(
                            _is_within(module, forbidden),
                            f"{path} must not import {forbidden}",
                        )

    def test_cli_imports_no_core_or_app(self) -> None:
        for module in _imports(PACKAGE / "cli.py"):
            for forbidden in (
                "byggleaf.app",
                "byggleaf.core",
            ):
                with self.subTest(imported=module):
                    self.assertFalse(
                        _is_within(module, forbidden),
                        f"cli.py must not import {forbidden}",
                    )

    def test_package_root_stays_uncluttered(self) -> None:
        root_modules = {path.name for path in PACKAGE.glob("*.py")}
        self.assertEqual(root_modules, {"__init__.py", "app.py", "cli.py"})
        self.assertTrue((CORE / "scaffold.py").is_file())
        self.assertFalse((PACKAGE / "scaffold.py").exists())

    def test_only_app_imports_cli(self) -> None:
        for path in _python_files(PACKAGE):
            if path.name == "app.py":
                continue
            imports = _imports(path)
            self.assertFalse(
                any(_is_within(module, "byggleaf.cli") for module in imports),
                f"{path} imports the CLI; only app.py may do that",
            )

    def test_app_is_the_assembler(self) -> None:
        imports = _imports(PACKAGE / "app.py")
        self.assertTrue(any(_is_within(module, "byggleaf.cli") for module in imports))
        self.assertTrue(any(_is_within(module, "byggleaf.core") for module in imports))
        self.assertTrue(
            any(_is_within(module, "byggleaf.core.scaffold") for module in imports)
        )

    def test_import_graph_has_no_cycles(self) -> None:
        graph = _import_graph()
        state: dict[str, int] = {}

        def visit(node: str) -> None:
            if state.get(node) == 1:
                self.fail(f"import cycle detected at {node}")
            if state.get(node) == 2:
                return
            state[node] = 1
            for neighbour in graph.get(node, ()):
                visit(neighbour)
            state[node] = 2

        for node in graph:
            visit(node)

    def test_only_approved_third_party_packages(self) -> None:
        for path in _python_files(PACKAGE):
            for module in _imports(path):
                top_level = module.split(".", 1)[0]
                if top_level == "byggleaf" or top_level in sys.stdlib_module_names:
                    continue
                with self.subTest(file=path.name, imported=module):
                    self.assertIn(
                        top_level,
                        APPROVED_THIRD_PARTY,
                        f"{path} imports unapproved dependency {top_level!r}",
                    )


class StaticAssetTests(unittest.TestCase):
    def test_no_javascript_files_are_shipped(self) -> None:
        javascript = [
            path
            for path in PACKAGE.rglob("*")
            if path.suffix.lower() in {".js", ".mjs", ".cjs", ".ts"}
        ]
        self.assertEqual(javascript, [])

    def test_templates_and_css_contain_no_javascript_or_web_fonts(self) -> None:
        forbidden = (
            "<script",
            "javascript:",
            "onclick=",
            "onload=",
            "@import",
            "@font-face",
            "fonts.googleapis",
            "fonts.gstatic",
            "http://",
            "https://",
        )
        for directory in (TEMPLATES, ASSETS):
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or path.suffix.lower() not in {
                    ".html",
                    ".css",
                }:
                    continue
                text = path.read_text(encoding="utf-8").lower()
                for needle in forbidden:
                    with self.subTest(file=path.name, needle=needle):
                        self.assertNotIn(needle, text)

    def test_design_tokens_are_exact(self) -> None:
        css = (ASSETS / "css" / "style.css").read_text(encoding="utf-8")
        for token in (
            "--color-forest-ink: #243D32",
            "--color-living-leaf: #8FA889",
            "--color-paper-ivory: #F4F0E6",
            "--color-graphite-ink: #303832",
            "--color-terracotta: #C47B52",
            "--measure: 65ch",
        ):
            with self.subTest(token=token):
                self.assertIn(token, css)
        self.assertIn("Georgia", css)
        self.assertIn("Songti SC", css)
        self.assertIn("max-width: 65ch", css)

    def test_data_directories_contain_no_python(self) -> None:
        for directory in (ASSETS, TEMPLATES, PACKAGE / "resources", LOCALES):
            for path in directory.rglob("*.py"):
                self.fail(f"Python logic belongs outside data dirs: {path}")

    def test_builtin_locales_use_canonical_language_codes(self) -> None:
        locale_files = sorted(LOCALES.glob("*.toml"))
        self.assertTrue(locale_files)
        for path in locale_files:
            with self.subTest(locale=path.name):
                self.assertEqual(path.stem, canonicalize_language(path.stem))

    def test_license_and_ci_are_declared(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(project["project"]["license"], "GPL-3.0-or-later")
        self.assertTrue((ROOT / "LICENSE").is_file())
        self.assertTrue((ROOT / ".github/workflows/ci.yml").is_file())

    def test_templates_stay_flat_and_simply_named(self) -> None:
        expected = {
            "base.html",
            "404.html",
            "home.html",
            "page.html",
            "post.html",
            "postlist.html",
        }
        actual = {
            path.name
            for path in TEMPLATES.iterdir()
            if path.is_file() and path.suffix == ".html"
        }
        self.assertEqual(actual, expected)
        self.assertFalse(
            any(path.is_dir() for path in TEMPLATES.iterdir()),
            "template subdirectories are unnecessary at this size",
        )
        self.assertFalse(
            any("-" in name for name in actual),
            "template names should avoid hyphenated compounds",
        )

    def test_package_data_is_declared_for_wheels(self) -> None:
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        patterns = project["tool"]["setuptools"]["package-data"]["byggleaf"]
        joined = "\n".join(patterns)
        for expected in (
            "assets/css/*.css",
            "assets/img/*",
            "templates/*.html",
            "resources/*.toml",
            "resources/*.md",
            "locales/*.toml",
        ):
            with self.subTest(pattern=expected):
                self.assertIn(expected, joined)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
