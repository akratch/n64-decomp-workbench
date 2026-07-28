# Castlevania 64 decomp.me scratch bundles

These bundles were generated locally from a legally obtained US 1.0 ROM and
the pinned CV64 checkout. Nothing was uploaded automatically.

| Symbol | State | Instructions | Normalized distance | Word mismatches |
|---|---:|---:|---:|---:|
| `menuButton_selectNextOption` | punch-in | 62/63 | 2 | 57 |
| `func_8013B270_BE460` | exact | 19/19 | 0 | 0 |
| `func_800012C0_1EC0` | exact | 6/6 | 0 | 0 |
| `func_800010A0_1CA0` | punch-in | 10/10 | 2 | 2 |
| `func_800010C8_1CC8` | punch-in | 18/18 | 2 | 2 |

Each symbol directory contains `target.s`, a complete `context.c`, `source.c`,
manual paste instructions, a JSON manifest, checksums, and `workbench.json`.
The non-exact cases are deliberately retained as useful manual punching-in
targets.
