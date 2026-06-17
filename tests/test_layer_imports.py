"""Reglas de importación entre capas."""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _imports_in_package(rel_dir: str) -> list[tuple[str, str]]:
    base = ROOT / rel_dir
    found = []
    for path in base.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                found.append((str(path.relative_to(ROOT)), node.module))
    return found


class LayerImportRulesTest(unittest.TestCase):
    def test_interface_does_not_import_persistence(self):
        bloqueados = ("expendedora.persistence", "infra.", "User_management")
        excepciones = (
            "expendedora/interface/auth/login.py",
            "expendedora/interface/auth/register.py",
            "expendedora/interface/auth/user_management.py",
        )
        for archivo, modulo in _imports_in_package("expendedora/interface"):
            if archivo.replace("\\", "/") in excepciones:
                continue
            for prefijo in bloqueados:
                self.assertFalse(
                    modulo.startswith(prefijo),
                    f"{archivo} importa {modulo}",
                )

    def test_logic_does_not_import_interface(self):
        for archivo, modulo in _imports_in_package("expendedora/logic"):
            self.assertFalse(
                modulo.startswith("expendedora.interface"),
                f"{archivo} importa {modulo}",
            )

    def test_persistence_does_not_import_logic_services(self):
        for archivo, modulo in _imports_in_package("expendedora/persistence"):
            self.assertFalse(
                modulo.startswith("expendedora.logic.services"),
                f"{archivo} importa {modulo}",
            )
