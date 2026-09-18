# Baseline figures

Baseline figures are grouped by pipeline run under:

```text
figures/baseline/<geography>_in_<study_area>/
```

The following directories are produced by the corresponding scripts:

| Output directory | Producing script |
| --- | --- |
| `lineplots/` | [`generate_figures.py`](../../experiment_code/baseline/visualization/line_plots/generate_figures.py) |
| `grid_lineplots/` | [`generate_figures.py`](../../experiment_code/baseline/visualization/line_plots/generate_figures.py) |
| `metric_family_grids/` | [`generate_figures.py`](../../experiment_code/baseline/visualization/line_plots/generate_figures.py) |
| `metrics_vs_rho/` | [`metrics_vs_rho.py`](../../experiment_code/baseline/visualization/metrics_vs_rho/metrics_vs_rho.py) |
| `rank_comparisons/` | [`rank_comparisons_single.py`](../../experiment_code/baseline/visualization/rank_comparisons/rank_comparisons_single.py) |
| `latex_tables/` | [`latex_table_one_year.py`](../../experiment_code/baseline/visualization/latex_tables/latex_table_one_year.py) and [`latex_table_all_years.py`](../../experiment_code/baseline/visualization/latex_tables/latex_table_all_years.py) |
| `figures/baseline/lambda_rankings/` | [`rank_lambdas.py`](../../experiment_code/baseline/visualization/lambda_scripts/rank_lambdas.py) |

See the [baseline visualization guide](../../experiment_code/baseline/visualization/README.md) for input requirements and runnable commands.
