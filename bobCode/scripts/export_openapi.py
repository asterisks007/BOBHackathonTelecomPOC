"""Export OpenAPI specification to openapi/skills_spec.json."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("USE_MOCK", "true")

from api.main import app  # noqa: E402

spec = app.openapi()
out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "openapi", "skills_spec.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(spec, f, indent=2)

path_count = len(spec.get("paths", {}))
print(f"Exported {path_count} API paths to openapi/skills_spec.json")
