/* Synthetic lever-sweep fixture (CC0); no game code. Compiled only by the
 * stand-in compiler beside it, never by IDO. */
extern int table[16];

int demo(int n, int *p) {
    int acc;
    int tmp;
    acc = n + 1;
    tmp = p[2];
    acc = acc + tmp;
    return acc;
}
