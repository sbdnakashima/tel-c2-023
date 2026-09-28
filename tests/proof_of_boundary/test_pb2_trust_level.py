# PB-2: S-1 required_trust_level — 全ノードが VERIFIED_EXTERNAL を宣言すること

import importlib
import inspect
import pkgutil

import pytest

from framework.nodes.base_node import BaseNode
from framework.schemas.trust_level import TrustLevel


def _discover_node_classes() -> list[type]:
    try:
        pkg = importlib.import_module("src.nodes")
    except ImportError:
        return []

    discovered = []
    for _, modname, _ in pkgutil.walk_packages(pkg.__path__, prefix="src.nodes."):
        module = importlib.import_module(modname)
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseNode)
                and attr is not BaseNode
                and attr.__module__ == modname
                and not inspect.isabstract(attr)
            ):
                discovered.append(attr)
    return discovered


class TestTrustLevel:
    """PB-2: 全ノードが required_trust_level = VERIFIED_EXTERNAL を宣言する。"""

    def test_all_nodes_declare_verified_external(self):
        node_classes = _discover_node_classes()
        if not node_classes:
            pytest.skip("no concrete BaseNode subclasses found under src/nodes/")

        violations = []
        for cls in node_classes:
            trust = getattr(cls, "required_trust_level", None)
            if trust != TrustLevel.VERIFIED_EXTERNAL:
                violations.append(f"{cls.__name__}: required_trust_level={trust!r} (expected VERIFIED_EXTERNAL)")

        assert not violations, "Trust level violations:\n" + "\n".join(violations)
