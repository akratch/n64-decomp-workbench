# Castlevania 64 campaign record

This is a code-free record of five workbench investigations performed against
[`k64ret/cv64`](https://github.com/k64ret/cv64) commit
`5307217aa772019b7576cad3cb2c545e88e0394a` with IDO 7.1 and these flags:

```text
-Wab,-r4300_mul -non_shared -G0 -Xcpluscomm -mips2 -O2
```

The generated contexts, target assembly, and candidate source are deliberately
not distributed. Their redistribution terms were not established. See the
[notice](NOTICE.md). Aggregate measurements are preserved in
[`results.json`](results.json); they are historical observations, not fresh CLI
reports or redistributable scratch inputs.

## Results

| Symbol | State | Candidate/target instructions | Normalized distance | Word mismatches |
|---|---:|---:|---:|---:|
| `menuButton_selectNextOption` | punch-in | 62/63 | 2 | 57 |
| `func_8013B270_BE460` | exact | 19/19 | 0 | 0 |
| `func_800012C0_1EC0` | exact | 6/6 | 0 | 0 |
| `func_800010A0_1CA0` | punch-in | 10/10 | 2 | 2 |
| `func_800010C8_1CC8` | punch-in | 18/18 | 2 | 2 |

The campaigns supplied five reusable findings:

- terminal zero padding after the final return delay slot must not be counted
  as part of an unsized function;
- one early missing instruction can make positional word mismatch look much
  larger than normalized edit distance;
- alias-preserving temporaries can recover exact reload topology;
- matching instruction count, opcodes, and registers can leave a genuinely
  independent scheduling residue; and
- several static-recomp releases producing identical objects is evidence about
  that tested axis, not proof that every authentic compiler lineage is
  equivalent.

These findings are captured in the synthetic fixtures and general workbench
rules, where they can be tested without redistributing project inputs.

## Reproduce locally

Maintainers who have a lawful local CV64 checkout and ROM-derived inputs can
create their own upload-neutral bundle:

```sh
decomp-workbench bundle-scratch output/function \
  --target-assembly target.s \
  --context ctx.c \
  --source candidate.c \
  --platform n64 \
  --compiler 'IDO 7.1' \
  --compiler-flags='-Wab,-r4300_mul -non_shared -G0 -Xcpluscomm -mips2 -O2' \
  --diff-label function_name \
  --project 'k64ret/cv64@5307217aa772019b7576cad3cb2c545e88e0394a'
```

The output directory must be new or empty, and
`decomp-workbench check-scratch output/function` verifies the resulting local
handoff without uploading it.
