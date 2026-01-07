---
trigger: always_on
---

- Everytime you write a python test, use pytest and the BDD `Given / When / Then` blocks and structure the tests to follow them. Also use pytest-mock if you need mocks and reuse them in fixture where appropiate. And, in general, any pytest extension where available.
- The BDD structure needs to have explanations of what they do. Example:
```
# Given a user
...

# When the user visits a website
...

# Then the website is rendered
...
```
- The `Given / When / Then` srtucture can include `And`s where necessary
- Tests don't need typing or params documentation