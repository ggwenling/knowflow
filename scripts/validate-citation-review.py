"""Validate independent citation review worksheets and optionally export v2 reviews."""
from citation_review import validate_main
from quality_common import run_cli

if __name__ == "__main__":
    raise SystemExit(run_cli(validate_main))
