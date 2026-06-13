# Truthful Build Doctrine

## Core Invariant

Every public claim about this project must be backed by executable code, reproducible output, committed tests, or clearly labeled nonfunctional design/spec material.

Unsupported claims are defects.

A README is not marketing copy. It is an interface contract with the user, the developer, GitHub, and the public.

## Rules

- No vaporware claims. Use `Planned`, `Experimental`, `Design target`, or `Currently unsupported` when code is incomplete.
- No fake logs, test summaries, screenshots, benchmark output, or demo output.
- No README inflation. Describe what exists, how to run it, what it does not do, limitations, and reproduction steps.
- No burden shifting. Document required dependencies, credentials, environment variables, setup steps, and unsupported paths.
- No deception by omission. If a command works only after extra setup, document that setup before the command.

## Release Gate

Before public pushes, releases, demos, or README-affecting pull requests, run:

```bash
scripts/truthfulness.sh
```

If that command fails, either fix the implementation or correct the documentation.
