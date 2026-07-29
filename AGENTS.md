# Repository Instructions

## Hard Rule: Never Publish Deployment Domains

This rule is mandatory and has no exceptions.

- Never commit, publish, or repeat any real deployment domain, subdomain, hostname, dynamic-DNS name, public IP address, or deployment URL belonging to this project or its owner.
- This prohibition applies to source code, configuration, manifests, documentation, examples, tests, fixtures, generated files, logs, commit messages, pull-request text, review replies, issue text, and screenshots.
- Treat deployment identifiers as sensitive information even when the service itself is intended to be publicly reachable.
- Use runtime environment variables or secret/configuration stores for real deployment values. In repository files, use only neutral placeholders such as `${BASE_DOMAIN}`, `<domain>`, or reserved example domains such as `example.com`.
- Never use a real value as an example, fallback, default, test fixture, or commented-out value.
- Before committing or publishing, inspect both the staged changes and the complete pull-request diff for deployment identifiers.
- If a real deployment identifier is discovered, do not repeat it in discussion. Notify the repository owner privately and replace it with a safe placeholder.

All contributors, automation, coding agents, and reviewers must enforce this rule.
