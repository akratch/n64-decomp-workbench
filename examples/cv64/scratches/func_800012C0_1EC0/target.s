glabel func_800012C0_1EC0
    /* 1EC0 800012C0 8C820004 */  lw         $v0, 0x4($a0)
    /* 1EC4 800012C4 ACA20004 */  sw         $v0, 0x4($a1)
    /* 1EC8 800012C8 AC450000 */  sw         $a1, 0x0($v0)
    /* 1ECC 800012CC AC850004 */  sw         $a1, 0x4($a0)
    /* 1ED0 800012D0 03E00008 */  jr         $ra
    /* 1ED4 800012D4 ACA40000 */   sw        $a0, 0x0($a1)
