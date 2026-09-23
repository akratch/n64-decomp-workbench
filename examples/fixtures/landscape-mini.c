/* Synthetic fixture for `sweep landscape --report`. Not derived from any
 * binary: it exists so the saved landscape beside it has a source whose
 * fingerprint can be checked. */
int landscape_mini(int *values, int count) {
    int total = 0;
    int i;
    for (i = 0; i < count; i++) {
        total += values[i];
    }
    return total;
}
