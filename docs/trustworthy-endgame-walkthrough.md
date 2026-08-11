# Trustworthy endgame walkthrough

This journey is synthetic and redistributable. It uses the checked-in
decomp.me export fixture for context diagnosis, then creates a temporary
experiment-v2 family, runs a required baseline control, records an exact
candidate, verifies exhaustive coverage, freshly finishes the immutable
winner, and packages it behind the passing finish receipt.

Run it from the repository root:

```sh
python3 examples/trustworthy-endgame/run.py
```

The final document reports `controls=PASS`,
`coverage=exhaustive-over-declared-space`, `finish=PASS`, and `package=PASS`.
The scratch fixture intentionally begins as a mismatch: the point of its first
stage is to prove that site metadata, scratch-object truth, and the unmeasured
project layer remain separate.

The generated campaign identifies compiler build, frontend, C dialect, driver,
and backend independently. Replace the synthetic values with an authentic
IRIX 4 `accom` cell or later `cfe` cell in a live project; sharing a wrapper or
later backend no longer merges their cache identities.

Nothing is uploaded or downloaded. The walkthrough needs no ROM, proprietary
compiler, target object, or network, and all state is removed with its
temporary directory. Its implementation is intentionally readable at
[run.py](../examples/trustworthy-endgame/run.py), so project maintainers can
adapt the same sequence without copying hidden test harness behavior.
