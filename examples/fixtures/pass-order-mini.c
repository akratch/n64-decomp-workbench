/* Synthetic fixture for `pass order`: the two-loop mini-TU shape, reduced to
 * one loop. pass-order-mini.s beside it is hand-written to show the reader
 * what a listing looks like; no compiler produced it. */
extern void f(int value);
extern void h(int value);
extern int arr[16];
extern int n, x;

void mini(void) {
    int i;
    i = 0;              /* @pass def i block=180 value=0 */
    f(i);               /* @pass read i block=180 */
    h(1);               /* @pass call block=181 */
    i &= 0;             /* @pass selfdef i block=181 value=0 */
    h(2);               /* @pass call block=182 */
    if (n != 0) {
        i = 0;          /* @pass def i block=184 value=0 */
        do {
            x += arr[i]; /* @pass loop i block=184 */
            i++;
        } while (i < 8);
    }
}
