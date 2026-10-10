"""
files.py - File workspace tools.
The agent can only read files inside WORKSPACE_DIR. Path traversal is rejected.
"""
import os
import re
import json
from pathlib import Path
from typing import Any

from app.config import WORKSPACE_DIR

try:
    from pypdf import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


def _safe_path(filename: str) -> Path:
    """
    Resolve filename relative to WORKSPACE_DIR and reject any path that escapes it.
    This is the single security enforcement point for file access.
    """
    workspace = Path(WORKSPACE_DIR).resolve()
    # Normalise separators — agent may send back Windows paths from search_files
    filename = filename.replace("\\", "/")
    candidate = (workspace / filename).resolve()
    if not str(candidate).startswith(str(workspace)):
        raise PermissionError(f"Access denied: '{filename}' is outside the workspace")
    return candidate


def search_files(query: str) -> dict[str, Any]:
    """
    Walk WORKSPACE_DIR and return files whose name or text content contains query.
    Returns at most 20 results. Paths use forward slashes so they work on all OSes.
    """
    workspace = Path(WORKSPACE_DIR).resolve()
    matches = []
    query_lower = query.lower()

    for root, _, files in os.walk(workspace):
        for fname in sorted(files):           # sorted for deterministic order
            fpath = Path(root) / fname
            # Always use forward slashes in returned paths
            rel = fpath.relative_to(workspace).as_posix()

            # 1. Filename match
            if query_lower in fname.lower():
                matches.append({"file": rel, "match": "filename"})
                continue

            # 2. Content match for text/json files
            if fname.endswith((".txt", ".json")):
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    if query_lower in content.lower():
                        matches.append({"file": rel, "match": "content"})
                except Exception:
                    pass

        if len(matches) >= 20:
            break

    return {"query": query, "results": matches}


def read_document(filename: str) -> dict[str, Any]:
    """
    Read a file from the workspace.
    Supports TXT, JSON (serialised to string), and PDF.
    Always returns 'content' as a string so extract_invoice_fields can process it.
    """
    try:
        path = _safe_path(filename)
    except PermissionError as e:
        return {"error": str(e)}

    if not path.exists():
        return {"error": f"File not found: {filename}"}

    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            if not PDF_SUPPORT:
                return {"error": "PDF support not available (pypdf not installed)"}
            reader = PdfReader(str(path))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return {"filename": filename, "content": text, "type": "pdf"}

        elif suffix == ".json":
            raw = path.read_text(encoding="utf-8", errors="ignore")
            # Return as string so extract_invoice_fields can regex over it
            return {"filename": filename, "content": raw, "type": "json"}

        else:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return {"filename": filename, "content": text, "type": "text"}

    except Exception as e:
        return {"error": f"Could not read {filename}: {e}"}


def extract_invoice_fields(text: str, use_llm: bool = True) -> dict[str, Any]:
    """
    Extract structured invoice fields from raw document text.
    When use_llm=True, delegates to the LLM provider with a strict output schema.
    Falls back to regex-based extraction if the LLM is unavailable.
    Never silently invents values — missing fields are returned as None.
    """
    # If text is accidentally a dict/list (e.g. from a JSON read), stringify it
    if not isinstance(text, str):
        text = json.dumps(text)

    def _regex_extract(t: str) -> dict:
        fields: dict[str, Any] = {
            "invoice_number": None,
            "vendor_name":    None,
            "invoice_date":   None,
            "due_date":       None,
            "amount":         None,
            "currency":       "INR",
            "description":    None,
            "po_reference":   None,
        }

        # Invoice number: must look like INV-XXX-YYYY-NNN or business-specific ID with digits/structure
        inv_m = re.search(
            r"invoice\s*(?:number|no\.?|#)?\s*[:\-]?\s*([A-Za-z0-9/\-]{3,30})",
            t, re.IGNORECASE
        )
        if inv_m:
            candidate_num = inv_m.group(1).strip()
            low_num = candidate_num.lower()
            disallowed = {"umber", "number", "invoice", "no", "unknown", "null"}
            has_digit = any(c.isdigit() for c in candidate_num)
            has_structure = "-" in candidate_num or "/" in candidate_num
            if low_num not in disallowed and len(candidate_num) >= 3 and (has_digit or has_structure):
                fields["invoice_number"] = candidate_num.upper()

        # PO Reference: e.g. "PO Reference: PO-GLOB-2024-015" or "PO Ref: PO-123"
        po_m = re.search(
            r"(?:po\s*reference|po\s*ref|purchase\s*order(?:\s*#|\s*ref)?|po\s*#)\s*[:\-]?\s*([A-Za-z0-9/\-]{3,30})",
            t, re.IGNORECASE
        )
        if po_m:
            candidate_po = po_m.group(1).strip().upper()
            if candidate_po.lower() not in {"reference", "ref", "none", "null"}:
                fields["po_reference"] = candidate_po

        # Dates — prefer labelled patterns first (Invoice Date / Due Date)
        inv_date_m = re.search(
            r"invoice\s*date\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            t, re.IGNORECASE
        )
        due_date_m = re.search(
            r"(?:due|payment)\s*date\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",
            t, re.IGNORECASE
        )
        if inv_date_m:
            fields["invoice_date"] = inv_date_m.group(1)
        if due_date_m:
            fields["due_date"] = due_date_m.group(1)

        # Fallback: grab first two ISO dates if labelled patterns not found
        if not fields["invoice_date"]:
            dates = re.findall(r"\b(\d{4}-\d{2}-\d{2})\b", t)
            if dates:
                fields["invoice_date"] = dates[0]
                if len(dates) > 1 and not fields["due_date"]:
                    fields["due_date"] = dates[1]

        # Amount — handles: "Amount: INR 45,000.00", "Total: 72,500", "₹45000"
        amt_m = re.search(
            r"(?:amount|total|subtotal|rs\.?|inr|₹)\s*[:\s]?\s*(?:inr\s*)?([0-9][0-9,]*(?:\.\d{1,2})?)",
            t, re.IGNORECASE
        )
        if amt_m:
            fields["amount"] = amt_m.group(1).replace(",", "")

        # Vendor: stop at newline so we don't swallow the whole document
        vendor_m = re.search(
            r"(?:from|vendor|supplier|bill(?:ed)?\s+(?:to|from))\s*[:\-]?\s*([A-Za-z][A-Za-z0-9\s&.,()-]{2,60})",
            t, re.IGNORECASE
        )
        if vendor_m:
            # Strip at first newline or trailing punctuation
            raw_vendor = vendor_m.group(1)
            raw_vendor = raw_vendor.split("\n")[0].strip().rstrip(",.")
            fields["vendor_name"] = raw_vendor[:60]

        # Description: first non-empty line after "Description:" label
        desc_m = re.search(r"description\s*[:\-]?\s*(.+)", t, re.IGNORECASE)
        if desc_m:
            fields["description"] = desc_m.group(1).strip()[:120]

        return fields

    if use_llm:
        try:
            from app.agent.llm import extract_with_llm
            return extract_with_llm(text)
        except Exception as e:
            fields = _regex_extract(text)
            fields["_extraction_method"] = f"regex_fallback (llm error: {e})"
            return fields
    else:
        fields = _regex_extract(text)
        fields["_extraction_method"] = "regex"
        return fields
