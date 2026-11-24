# GetSetMix

## Architecture

Architecture, the layer rules and the rule → check table:
`docs/architecture.md`, section 8.8. Read it before adding a module, a
helper or a layer. Module designs live in `docs/design/`.

- One definition per helper, constant, allowed value and asset: search
  first, then reuse or extend what exists.
- Dependencies follow 8.8: routes → core → base (`db`, `config`); the pure
  modules (`audiohash`, `matching`, `naming`, `genres`, `rules`) touch no
  storage; settings and environment variables are read only in `config.py`.
- CI ratchets the debt (ruff, pyright, import-linter, duplication, coverage,
  staticcheck). Never raise a ceiling; when a change lowers a count, lower
  its ceiling in the same pull request.
- Every test names what it protects, goes through the interface, and can
  fail. Check UI changes in a browser, not only with tests.
