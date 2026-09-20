"""Export SDK KYC models from the runtime contract, without importing the app.

Usage: python tools/export_kyc.py /path/to/legichain-python /path/to/backend
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(sys.argv[2]).resolve()
source = (ROOT / "src/legichain/api/kyc_schemas.py").read_text(encoding="utf-8")
tree = ast.parse(source)
definitions = {}
for node in tree.body:
    if isinstance(node, ast.ClassDef):
        definitions[node.name] = node
    elif isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                definitions[target.id] = node

selected = {
    "KYCApplicationCreateRequest", "KYCApplicationCreateResponse",
    "KYCApplicationStatusResponse", "KYCSubmitRequest", "KYCSubmitResponse",
    "DocumentSubmitRequest", "SelfieSubmitRequest", "NFCSubmitRequest",
    "LivenessChallengeRequest", "LivenessChallengeResponse", "LivenessSubmitRequest",
}
# The exported status class name is verified rather than silently omitted.
if "KYCApplicationStatusResponse" not in definitions:
    selected.remove("KYCApplicationStatusResponse")
    selected.add("KYCStatusResponse")
pending = list(selected)
while pending:
    name = pending.pop()
    node = definitions[name]
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in definitions and child.id not in selected:
            selected.add(child.id)
            pending.append(child.id)
imports = [ast.get_source_segment(source, n) for n in tree.body
           if isinstance(n, (ast.Import, ast.ImportFrom))]
parts = ['"""Generated KYC wire models. Source: Legichain API; do not edit by hand."""', *imports]
parts.extend(ast.get_source_segment(source, node) for node in tree.body
             if node in [definitions[name] for name in selected])
destination = Path(sys.argv[1]) / "legichain/kyc_models.py"
destination.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
print(f"Exported {len(selected)} KYC types to {destination}")
