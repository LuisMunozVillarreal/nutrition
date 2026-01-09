---
trigger: always_on
---

- As part of your implementation plan. Within the verification plan, as well as whatever you consider necessary; you need to connect to the CircleCI via its API for the project at hand and make sure the build has passed. Usually, whatever tasks the build runs can be run locally using make. Some of those make targets are in the `backend` directory, and some in the `webapp` one. In any case, once you've tested locally that all target pass, you need to trigger a build and double check that it also passes in CircleCI.
- To achieve the above, follow the workflow `make-circleci-green`
- Don't suggest manual verification of steps that you can do yourself by running the commands you're suggesting.