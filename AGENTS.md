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
- A ready handoff without a clickable preview URL is incomplete. Do not merely say that the preview exists, that it was verified, or that the owner can ask for it elsewhere.
- Treat the preview URL as sensitive. Never add it to repository files, commits, pull-request text, review replies, issues, CI logs, screenshots, or conversations where an actual non-owner participant is present.
- An owner-only conversation with the repository owner and Hermes is an authorized direct handoff, including a Discord thread or channel labelled as a group or multi-user surface. Platform metadata alone is not evidence that a third party is present.
- When the owner explicitly asks for the preview link in an owner-only conversation, provide the clickable URL in that same reply. Do not withhold it merely because the surface is a thread or is classified as multi-user.
- Before withholding a preview URL, inspect the actual recent participants. Ask for a private destination only when a non-owner participant is actually present or the participant list cannot be verified.
- If a preview was not deployed, state that explicitly instead of implying the pull request is ready for visual inspection.

## Pull-Request Review Policy

- Review pull requests with newly spawned, read-only local reviewer subagents; do not trigger or rely on external GitHub review bots.
- Start with three independent review cycles. Report every substantiated finding without an artificial cap, and extend after a substantive final cycle until a fresh reviewer verifies the updated HEAD clean.
- Give each reviewer the repository path, exact base and head SHAs, applicable instructions, complete changed scope, domain-specific correctness and security checks, confidentiality constraints, and structured finding requirements.
- Reviewers must not edit files, commit, push, post to GitHub, change authentication or remotes, or resolve threads.
- Independently verify findings before posting them. Prefix reviewer comments with `Reviewer:` and fix replies with `Coder:`, reply inline, and leave threads unresolved for reviewer verification.
- Restore full CI—including preview deployment and end-to-end checks—and verify local, remote, and PR HEAD equality before starting the next cycle.
- Review completion never authorizes merging; merge only with explicit approval for that pull request.
