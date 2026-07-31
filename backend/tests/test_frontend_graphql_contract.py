"""Validate frontend GraphQL documents against the backend schema."""

import re
from pathlib import Path

from graphql import parse, validate

from config.schema import schema

GQL_TEMPLATE = re.compile(r"\bgql\s*`(?P<document>.*?)`", re.DOTALL)
WEBAPP_SOURCE = Path(__file__).parents[2] / "webapp" / "src"


def test_embedded_frontend_graphql_documents_match_backend_schema():
    """Every static frontend GraphQL document validates against Strawberry."""
    documents = []
    for source_path in sorted(WEBAPP_SOURCE.rglob("*.ts*")):
        source = source_path.read_text(encoding="utf-8")
        for match in GQL_TEMPLATE.finditer(source):
            document = match.group("document")
            assert "${" not in document, (
                f"{source_path} contains a dynamic GraphQL document that this "
                "contract test cannot validate"
            )
            documents.append((source_path, document))

    assert documents, f"No GraphQL documents found under {WEBAPP_SOURCE}"

    failures = []
    for source_path, document in documents:
        errors = validate(
            schema._schema,  # pylint: disable=protected-access
            parse(document),
        )
        failures.extend(f"{source_path}: {error}" for error in errors)

    assert not failures, "\n\n".join(failures)
