extern u32 D_80341060[];

void func_800010A0_1CA0(void) {
    u32* current = D_80341060;

    do {
        current[1] = 0;
        current += 2;
    } while (current < (u32*) objects_array);
}
