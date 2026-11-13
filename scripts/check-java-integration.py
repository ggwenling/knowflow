"""Fail CI when a required Testcontainers suite did not actually run."""
from pathlib import Path
import sys
from xml.etree import ElementTree


SUITES = (
    "PostgreSqlMigrationIntegrationTest", "AuthKnowledgeBaseIntegrationTest",
    "DocumentApiIntegrationTest", "S3ObjectStoreIntegrationTest", "ApiSecurityIntegrationTest",
)


def main(directory):
    errors = []
    for suite in SUITES:
        reports = list(directory.glob(f"TEST-*.{suite}.xml"))
        if len(reports) != 1:
            errors.append(f"{suite}: expected one Surefire report, got {len(reports)}")
            continue
        result = ElementTree.parse(reports[0]).getroot().attrib
        if int(result["tests"]) < 1 or any(int(result[key]) for key in ("skipped", "errors", "failures")):
            errors.append(f"{suite}: tests={result['tests']}, skipped={result['skipped']}, "
                          f"errors={result['errors']}, failures={result['failures']}")
    if errors:
        raise SystemExit("\n".join(errors))
    print(f"Verified {len(SUITES)} Testcontainers suites")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
