"""
registry.py - Typed tool registry.

Every tool the agent can call is registered here with:
- input/output schemas
- permission requirements
- side-effect classification

The LLM selects tool names from this registry.
Tool arguments are validated against the schema BEFORE execution.
The LLM cannot add new tools or bypass permissions at runtime.
"""
from typing import Any, Callable
from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    name: str
    description: str
    # What permissions are needed to use this tool
    permissions: list[str]
    # Whether this tool changes external state (DB writes, etc.)
    has_side_effects: bool
    # The actual function to call; set after registration
    fn: Callable = field(default=None, repr=False)


# Central registry dict
_registry: dict[str, ToolSpec] = {}


def register(spec: ToolSpec):
    _registry[spec.name] = spec
    return spec


def get_tool(name: str) -> ToolSpec | None:
    return _registry.get(name)


def list_tools() -> list[str]:
    return list(_registry.keys())


def all_tools() -> list[ToolSpec]:
    return list(_registry.values())


# ── Register all tools ────────────────────────────────────────────────────────
# Functions are imported and attached in tools/__init__.py after definition.

TOOLS = [
    ToolSpec("search_files",        "Search sample_data for files matching a query", ["read"], False),
    ToolSpec("read_document",       "Read a file from the controlled workspace",     ["read"], False),
    ToolSpec("extract_invoice_fields", "Extract invoice fields from document text",  ["read"], False),
    ToolSpec("find_vendor",         "Find vendor by name (fuzzy match)",             ["read"], False),
    ToolSpec("search_invoices",     "Search invoices in the database",               ["read"], False),
    ToolSpec("get_invoice",         "Get a single invoice by ID",                    ["read"], False),
    ToolSpec("create_invoice",      "Create a new invoice in the finance system",    ["write"], True),
    ToolSpec("update_invoice_status", "Update invoice approval/payment status",      ["write"], True),
    ToolSpec("get_purchase_order",  "Get a purchase order by PO number or ID",       ["read"], False),
    ToolSpec("compare_invoice_with_po", "Compare invoice fields against a PO",       ["read"], False),
    ToolSpec("verify_invoice",      "Independently verify a stored invoice record",  ["read"], False),
    ToolSpec("request_approval",    "Request human approval for a sensitive action", ["write"], True),
]

for t in TOOLS:
    register(t)
