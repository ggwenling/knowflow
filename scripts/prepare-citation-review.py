"""Prepare independent citation review worksheets without overwriting originals."""
from citation_review import prepare_main
from quality_common import run_cli

if __name__ == "__main__":
    raise SystemExit(run_cli(prepare_main))
