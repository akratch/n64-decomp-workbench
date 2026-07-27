int dkwb_global[32];

int dkwb_fidelity_micro(int *values, int count, float scale) {
    int index;
    int sum = 0;
    float weighted = 0.0f;

    for (index = 0; index < count; index++) {
        int value = values[index];
        if (value > dkwb_global[index & 31]) {
            sum += value * (index + 3);
            weighted += (float) value * scale;
        } else {
            sum -= value;
            weighted -= (float) index;
        }
    }
    return sum + (int) weighted;
}
