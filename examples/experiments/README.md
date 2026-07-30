# Experiment manifest example

This synthetic family shows how an external generator describes deterministic
source variants without teaching the workbench to rewrite C. The source is
intentionally trivial; the useful artifact is the manifest contract:
parameters have declared choices, each candidate has one unique assignment,
and the protected region is a half-open instruction range.

Validate it without a compiler:

```sh
decomp-workbench experiment validate \
  examples/experiments/statement-grouping/experiment.json
```

A real campaign passes the same file with `--experiment-manifest`; status then
shows tested assignments, the declared space, family best, object-basin
collapse, and selected-region preservation. Keep generation project-specific:
emit new files in a working directory, never rewrite the active translation
unit in place.
