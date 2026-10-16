# Developing the kit

## Where to change it

Change the kit in its own repository, never inside a host's submodule.

## Before you push

1. Run the suite: `PYTHONPATH=<kit> python -B -m pytest -p no:cacheprovider tests -q`.
2. Verify the committed state in a clean worktree:

   ```text
   git -c core.longpaths=true worktree add --detach <scratch>/head HEAD
   ```

   Run the suite there, then remove the worktree.

## Rules a change keeps

- **No tool or driver name in generic code.** A tool or driver fact belongs to its driver or its
  catalogue. `test_one_home.py` and the agnosticism tests hold this.
- **Each new mechanism is proven with a fixture that the kit does not ship**, so it is proven to be
  extensible by declaration.
- **Remote behaviour is proven against the recorded transport**, unless a real host is available.
  What is not proven on a real host is written as such in the ADR's owed list and in
  `config/conformance.json`.
- **A breaking change bumps the major version** and carries a migration (`migrate`). Every release
  has a CHANGELOG entry and an ADR-001 amendment, with its rejected alternatives.

## How a host takes the change

1. Fast-forward its submodule.
2. Run `migrate` if the changelog says so.
3. Run `render`, then `validate`.
