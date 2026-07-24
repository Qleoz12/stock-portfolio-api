import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from analytics.export.notebook_exporter import build_notebook, validate_notebook_syntax

run_dir = Path("analytics_runs/098806fc-a5e")
result = json.loads((run_dir / "result.json").read_text(encoding="utf-8"))
data = json.loads((run_dir / "data.json").read_text(encoding="utf-8"))
nb = build_notebook(result["run_id"], result, data)
errors = validate_notebook_syntax(nb)
print("ERRORS:", errors)
if errors:
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] == "code":
            src = "".join(cell["source"])
            try:
                compile(src, f"cell_{i}", "exec")
            except SyntaxError as e:
                print(f"=== Cell {i} line {e.lineno} ===")
                print(src)
                print("---")
