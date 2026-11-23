# city_reps_dbt

The dbt project for City Reps. See the [main README](../README.md) for the architecture, models, design decisions and how to run it.

Quick commands, from this folder:

```bash
dbt build                      # build every seed and model, and run every test
dbt build -s +dim_spots        # dim_spots and everything it depends on
dbt docs generate && dbt docs serve   # browsable docs with a lineage graph
```
