int values[8];
int *first(void) { return &values[1]; }
int *second(void) { return &values[1]; }
int combine(int n) { int *a = &values[1]; int *b = &values[2]; return a[n & 1] + *b; }
