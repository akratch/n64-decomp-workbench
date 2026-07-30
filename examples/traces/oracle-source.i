# 1 "candidate.c"
int format_value(int width, int length)
{
    int padding = width - length;
    while (padding-- > 0) {
        width += 1;
    }
    return width + length;
}
