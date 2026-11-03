"""Check that the candidate OpenAPI describes the checked-in controller routes."""
import ast
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "contracts/openapi-draft10.json"


class OpenApiDraft10Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = json.loads(SPEC.read_text(encoding="utf-8"))
        cls.definitions = json.loads((ROOT / "contracts/schemas/protocol.schema.json").read_text(encoding="utf-8"))["$defs"]

    def test_registered_controller_and_ai_routes_are_present(self):
        declared = {(method, path) for path, ops in self.spec["paths"].items() for method in ops}
        java = ROOT / "services/api/src/main/java/com/knowflow/api"
        expected = set()
        for file in java.rglob("*Controller.java"):
            text = file.read_text(encoding="utf-8")
            prefix_match = re.search(r'@RequestMapping\("([^\"]+)"\)', text)
            prefix = prefix_match.group(1) if prefix_match else ""
            for match in re.finditer(r'@(Get|Post|Delete|Put|Patch)Mapping(?:\(([^)]*)\))?', text):
                arg = match.group(2) or ""
                path_match = re.search(r'"([^\"]+)"', arg)
                expected.add((match.group(1).lower(), prefix + (path_match.group(1) if path_match else "")))
        tree = ast.parse((ROOT / "services/ai/src/knowflow_ai/app.py").read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                for decorator in node.decorator_list:
                    if (isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute)
                            and isinstance(decorator.func.value, ast.Name) and decorator.func.value.id == "app"
                            and decorator.func.attr in {"get", "post", "delete", "put", "patch"}
                            and decorator.args and isinstance(decorator.args[0], ast.Constant)):
                        expected.add((decorator.func.attr, decorator.args[0].value))
        self.assertEqual(declared, expected)

    def test_path_parameters_and_schema_references_resolve(self):
        self.assertEqual(self.spec["openapi"], "3.1.0")
        for path, operations in self.spec["paths"].items():
            expected = set(re.findall(r"\{([^}]+)\}", path))
            for operation in operations.values():
                found = {p["name"] for p in operation.get("parameters", [])
                         if p.get("in") == "path" and p.get("required") is True}
                self.assertEqual(found, expected, path)

        def walk(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    ref = value["$ref"]
                    if ref.startswith("./schemas/protocol.schema.json#/$defs/"):
                        self.assertIn(ref.rsplit("/", 1)[-1], self.definitions)
                    elif ref.startswith("#/components/"):
                        cursor = self.spec
                        for key in ref[2:].split("/"):
                            cursor = cursor[key]
                    else:
                        self.fail(f"unexpected reference {ref}")
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(self.spec)

    def test_security_and_service_ownership(self):
        self.assertEqual(self.spec["security"], [{"userBearer": []}])
        for path, operations in self.spec["paths"].items():
            for operation in operations.values():
                if path.startswith("/internal/"):
                    self.assertEqual(operation["security"], [{"internalBearer": []}], path)
                if path == "/health/live" or path.startswith("/internal/") and not path.startswith("/internal/v1/tasks/"):
                    self.assertEqual(operation["servers"][0]["url"], "http://localhost:8000", path)

    def test_public_stream_and_source_locators_use_shared_closed_schema(self):
        schemas = self.spec["components"]["schemas"]
        self.assertEqual(
            schemas["PublicStreamEvent"]["$ref"],
            "./schemas/protocol.schema.json#/$defs/AnswerStreamEvent")
        self.assertEqual(
            schemas["PublicSource"]["properties"]["locator"]["$ref"],
            "./schemas/protocol.schema.json#/$defs/Locator")


if __name__ == "__main__":
    unittest.main()
