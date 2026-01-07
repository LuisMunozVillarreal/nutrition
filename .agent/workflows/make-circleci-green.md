---
description: Fix issues until CircleCI is green
---

1. Using the CircleCI PAT that you can find running `secret-tool lookup service circleci`, check if the last build for the current branch have all tasks as green
2. If it wasn't, check the logs and fix whatever necessary (remember that every task in CircleCI executes a make target, so you can check things locally as well)
3. Commit and push
4. Go to 1 until the build is green