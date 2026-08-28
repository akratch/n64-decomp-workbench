# Project configuration

Use a project config when you repeatedly diagnose the same target/candidate
pair. It keeps paths, symbol scope, section, and objdump identity visible in a
small checked-in file without teaching the workbench how to run an opaque
project build.

Start with discovery. It is a preview and does not write anything:

```sh
decomp-workbench project init . \
  --target build/reference.o \
  --candidate build/current.o \
  --symbol function_name
```

The preview reports recognized `objdiff.json`, Splat YAML, and Make/Just build
metadata. It deliberately does not select an objdiff unit or infer an object
pair: a real project commonly has hundreds, and a plausible guess would make a
wrong comparison look authoritative. Add the explicit values, inspect the TOML,
then write it:

```sh
decomp-workbench project init . \
  --target build/reference.o \
  --candidate build/current.o \
  --symbol function_name \
  --objdump /path/to/mips-linux-gnu-objdump \
  --write
```

The command creates `.decomp-workbench.toml` exclusively and refuses to
overwrite an existing file. Paths are relative to the config directory, so
the file is portable across clones. Unknown sections and misspelled keys are
errors rather than silently ignored settings.

Run the configured object loop from the project root or any child directory:

```sh
decomp-workbench project show
decomp-workbench project next
decomp-workbench project diagnose
decomp-workbench project compare -- --show-diff
```

`--print-command` expands a configured command without running it. This is the
right inspection surface for scripts and agents:

```sh
decomp-workbench project diagnose --print-command
```

For retained GNU objdump text, add `--dumps` during init. Configured commands
then select `next-dumps`, `compare-dumps`, and `diagnose-dumps` automatically;
an objdump executable is neither needed nor accepted in that mode.

To make the campaign loop reusable too, include the compile-one template and
its scientific identity before the config's first `--write` (or edit the TOML
explicitly later). Discovery never turns a generic `make` file into a guessed
compile command:

```sh
decomp-workbench project init . \
  --target build/reference.o \
  --symbol function_name \
  --compile-command './compile-one {source} {output}' \
  --compile-cwd . \
  --env GAME_VERSION=us \
  --inherit-env PATH \
  --compiler-id ido-5.3 \
  --frontend 'IRIX 4.1 accom' \
  --language c89 \
  --driver cc-irix4 \
  --backend 'IDO 5.3 uopt/ugen/as1' \
  --write

decomp-workbench project campaign candidates/*.c
```

The expanded campaign uses the configured target, command/cwd, sealed fixed
environment, named host inheritance, compiler lineage, objdump, symbol,
section, state/cache locations, and source-retention policy. Use
`project campaign ... --print-command` to audit it without compiling.

## Supported file

```toml
[project]
name = "example-game"

[object]
input_mode = "objects"
target = "build/reference.o"
candidate = "build/current.o"
symbol = "function_name"
section = ".text"
objdump = "/opt/cross/bin/mips-linux-gnu-objdump"

[build]
command = ["./compile-one", "{source}", "{output}"]
cwd = "."
env = ["GAME_VERSION=us"]
inherit_env = ["PATH"]

[compiler]
id = "ido-5.3"
frontend = "IRIX 4.1 accom"
language = "c89"
driver = "cc-irix4"
backend = "IDO 5.3 uopt/ugen/as1"

[campaign]
state_dir = ".decomp-workbench"
cache_dir = ".decomp-workbench/cache"
retain_sources = "leaders"

[permuter]
make = "gmake"
permuter_dir = "tools/permuter"
object_template = "build/{source}.o"
compiler_marker = "tools/ido/cc"
compiler_command = "tools/ido/cc -c -non_shared -G 0 -I include -DVERSION_us"
assembler_command = "tools/binutils/mips64-elf-as -march=vr4300 -32 -G0"
preserve_macros = ["g[DS]P.*=void"]
preserve_macro_modes = ["configured", "none"]
fallback_flags = ["-O2", "-mips2", "-32"]
ranking = "config/ranking.json"
output_dir = ".decomp-workbench/permute"
minutes = 20
jobs = 1
load_threshold = 9.0
```

`[permuter]` is consumed only by `permute-sweep` and `permute-doctor`; see
[Permuter sweeps](permute-sweep.md) for what each key does. It deliberately
holds no codegen flags: those are recovered per object from the project's own
build, because a static flag table is wrong exactly when it matters.

`project next`, `compare`, and `diagnose` consume `[object]`; `project campaign`
also consumes `[build]`, `[compiler]`, and `[campaign]`. Nothing runs a build
implicitly: only the explicit `project campaign` command dispatches the
configured compiler. Record IRIX 4 `accom` and a later `cfe` as different
frontend configs even when they feed the same backend; see [Alternate
authentic frontends](alternate-frontends.md).

Configuration reduces repetition, not evidence. Every command still emits the
resolved target and candidate, and `project show --json` gives automation a
versioned, absolute-path view of what will be used.
