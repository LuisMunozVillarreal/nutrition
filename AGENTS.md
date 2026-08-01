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

## Pull-Request Ready Handoff

When reporting that a pull request is ready:

- Do not call it ready until the terminal preview-environment CI job has succeeded.
- Retrieve and verify the deployed preview URL from the deployment system.
- Include the pull-request URL, deployed preview URL, and final CI status in the direct handoff to the repository owner so the change can be inspected immediately.
- Treat the preview URL as sensitive. Share the real value only in the owner's direct handoff; never add it to repository files, commits, pull-request text, review replies, issues, CI logs, screenshots, or public/multi-user channels. If the current channel is not private, ask the owner where to send it.
- If a preview was not deployed, state that explicitly instead of implying the pull request is ready for visual inspection.

## Codex Review Trigger

When requesting a Codex review for this repository, post this exact comment:

```text
@codex review for correctness, security, authorization, data integrity, nutrition calculations and unit conversions, Django/GraphQL/Next.js contract regressions, database migrations, and deployment or preview-environment regressions. Follow all applicable AGENTS.md instructions. If you detect a sensitive deployment identifier, do not quote or reproduce it.
```
