---
trigger: always_on
---

- As part of your implementation plan. Within the verification plan, as well as whatever you consider necessary; you need to connect to the CircleCI via its API for the project at hand and make sure the build has passed. Usually, whatever tasks the build runs can be run locally using make
- To achieve the above, follow the workflow `make-circleci-green`
- Don't suggest manual verification of steps that you can do yourself by running the commands you're suggesting.