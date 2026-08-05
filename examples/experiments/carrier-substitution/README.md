# Carrier-substitution composition

This redistributable toy models the cleanup discovered after the SSSV
`func_802963D0_6A7A80` function was already instruction-exact. It is a source
generation example, not an N64 matching claim.

Inspect and generate the three bounded candidates:

```sh
decomp-workbench experiment inspect-source baseline.c
decomp-workbench experiment compose composition.json generated --dry-run
decomp-workbench experiment compose composition.json generated
decomp-workbench experiment validate generated/experiment.json
```

The pair combines two families that earlier searches had tested separately:
carrier substitution and deletion of a now-redundant tail use. Compilation is
deliberately a separate campaign step because a literal source edit is not
evidence of a compiler effect.
