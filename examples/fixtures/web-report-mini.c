/* Synthetic source for examples/traces/web-report.log (CC0, no game code).
 * Hand-written to give the records beside it line numbers to point at: the
 * records were written by hand and were not produced by compiling this file.
 * Locals sit at frame offsets col=-28, index=-32, sum=-36; grid is param 0. */
extern int lookup(int value);

int mini_web(int *grid, int n) {
    int col;
    int index;
    int sum;
    col = n * 3;
    sum = 0;
    index = col & 7;
    while (index < 40) {
        sum += grid[index];
        index += col & 7;
    }
    sum += lookup(col & 7);
    return sum + index;
}

int mini_other(int n) {
    return n + 1;
}
