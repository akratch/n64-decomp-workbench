s32 menuButton_selectNextOption(s32* option, s16* selection_delay_timer, s16 num_options) {
    s32 ret = 0;
    s32 roll_over;

    *selection_delay_timer = 0;

    if (num_options < 0) {
        num_options *= -1;
        roll_over = FALSE;
    } else {
        roll_over = TRUE;
    }

    ret = 0;
    if (moveSelectionCursor(CONT_UP)) {
        *option -= 1;

        if (*option < 0) {
            ret = -1;

            if (roll_over) {
                *option = num_options - 1;
            } else {
                *option = 0;
            }
        }
    }

    if (moveSelectionCursor(CONT_DOWN)) {
        *option += 1;

        if (*option >= num_options) {
            ret = 1;

            if (roll_over) {
                *option = 0;
            } else {
                *option = num_options - 1;
            }
        }
    }

    return ret;
}
