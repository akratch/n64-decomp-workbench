# Trustworthy endgame example

This asset-free example runs the complete scratch-check, controlled-campaign,
fresh-finish, and receipt-gated packaging journey:

```sh
python3 examples/trustworthy-endgame/run.py
```

It creates all state in a temporary directory, performs no network operation,
and uses no ROM, game object, or proprietary compiler. The expected final JSON
and an explanation of each gate are in the
[walkthrough](../../docs/trustworthy-endgame-walkthrough.md).
