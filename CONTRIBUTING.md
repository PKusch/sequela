# Contributing

The most useful thing you can send is a task the benchmark gets wrong: a case
where the oracle's answer is not the answer a careful person would give, or where
a policy can score well without knowing anything. Open an issue with the tool, the
arguments and what you expected.

## How the data is made

Nothing in `data/` is edited by hand. Both files are built from the catalogue and
CI rebuilds them and fails if the committed copy is different.

- `sequela/catalogue.py` holds the tools, the scenarios and the injected
  sentences. Every scenario is written by hand and tagged with a `family`, so a
  result can be broken down by what went wrong and not only by which tool.
- `sequela/oracle.py` works out the true consequences of a call from the tool
  definition and the arguments. It never trusts anything the tool says about
  itself.
- `sequela/generate.py` turns those into `data/tasks.jsonl` (the main set) and
  `data/heldout.jsonl` (sentences no reference policy has been tuned on).

## Adding a task

1. Add the tool, or the scenario, in `sequela/catalogue.py`.
2. Rebuild the data and check it:

   ```bash
   python -m sequela.run generate
   python -m sequela.run check
   ```

3. Run the tests and the reference policies. The README quotes their numbers, so a
   change that moves them needs the README changed in the same commit:

   ```bash
   python -m unittest discover -s tests
   for p in oracle uncoupled trusting name_reader schema_blind paranoid memorised; do
     python -m sequela.run run reference:$p --out /tmp/$p.json
   done
   python -m sequela.run report /tmp/*.json
   ```

## Keep out of the repo

Results from a live model go in `results/live/`, which is git-ignored so a reading
can never be committed by accident. Add one deliberately with `git add -f`, and put
the number in the README table by hand.
