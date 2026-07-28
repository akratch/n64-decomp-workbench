# decomp.me scratch bundle

Project: `k64ret/cv64@5307217aa772019b7576cad3cb2c545e88e0394a`.

This directory is upload-neutral: creating it does not contact decomp.me.

1. Open <https://www.decomp.me/new>.
2. Select platform `n64` and select compiler `IDO 7.1`.
3. Use diff label `func_800010C8_1CC8`.
4. Paste `target.s` into **Target assembly**.
5. Paste `context.c` into **Context**.
6. Create the scratch, then paste `source.c` into the source editor.
7. If a preset was not selected, use these compiler flags:

   ```text
   -Wab,-r4300_mul -non_shared -G0 -Xcpluscomm -mips2 -O2
   ```

Run `shasum -a 256 -c SHA256SUMS` before sharing to verify the three copied
inputs. `scratch.json` contains the same settings and content identities in a
machine-readable form.
