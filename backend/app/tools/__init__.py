"""
tools/__init__.py
Wires the tool functions into the registry so the agent can dispatch by name.
"""
from app.tools.registry import get_tool
from app.tools import files as file_tools
from app.tools import finance_tools


def _attach(name: str, fn):
    spec = get_tool(name)
    if spec:
        spec.fn = fn


_attach("search_files",            file_tools.search_files)
_attach("read_document",           file_tools.read_document)
_attach("extract_invoice_fields",  file_tools.extract_invoice_fields)
_attach("find_vendor",             finance_tools.find_vendor)
_attach("search_invoices",         finance_tools.search_invoices)
_attach("get_invoice",             finance_tools.get_invoice)
_attach("create_invoice",          finance_tools.create_invoice)
_attach("update_invoice_status",   finance_tools.update_invoice_status)
_attach("get_purchase_order",      finance_tools.get_purchase_order)
_attach("compare_invoice_with_po", finance_tools.compare_invoice_with_po)
_attach("verify_invoice",          finance_tools.verify_invoice)
# request_approval is handled specially inside the agent graph (not a regular tool fn)
