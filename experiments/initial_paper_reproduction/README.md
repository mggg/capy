# Initial paper reproduction

This directory preserves the original workflow used to produce the figures and
results in the initial paper submission.  It predates the automated pipeline
(`pipeline/experiment_orchestration.py`) and was executed manually — city-by-city via
Jupyter notebooks and standalone shell scripts rather than through a unified
experiment config.

## Contents

- `notebooks/` — exploratory and figure-generation notebooks (Chicago, Iowa,
  Metro Rankings, Leaf Graphs)
- `figures/` — figures generated from those notebooks
- `reproduction_figures_old/` — earlier figure versions kept for reference
- `scripts/` — ad-hoc shell scripts (`Chicago_Reproduce.sh`, `iowa.sh`)
  used to pre-process the Chicago and Iowa datasets

## Running

Because this workflow predates the current pipeline, the scripts reference
old paths and call modules that have since been renamed.  They are preserved
for historical reference; do not expect them to run without modification.

For new work building on these results, use `experiments/baseline/` as a
starting point and the automated pipeline via `scripts/run_experiment.sh`.
