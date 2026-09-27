extern float state;
extern int descriptor;
extern void consume(int *, float);
void control(int count, int skip) {
    int i;
    if (!skip) {
        for (i = 0; i < count; i++) {
            state += (-11.0f - state) * 0.125f;
        }
    }
    consume(&descriptor, state);
}
