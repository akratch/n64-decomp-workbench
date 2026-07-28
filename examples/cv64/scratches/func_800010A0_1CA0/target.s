glabel func_800010A0_1CA0
    /* 1CA0 800010A0 3C028034 */  lui        $v0, %hi(D_80341060)
    /* 1CA4 800010A4 3C038034 */  lui        $v1, %hi(objects_array)
    /* 1CA8 800010A8 24632060 */  addiu      $v1, $v1, %lo(objects_array)
    /* 1CAC 800010AC 24421060 */  addiu      $v0, $v0, %lo(D_80341060)
  .L800010B0_1CB0:
    /* 1CB0 800010B0 24420008 */  addiu      $v0, $v0, 0x8
    /* 1CB4 800010B4 0043082B */  sltu       $at, $v0, $v1
    /* 1CB8 800010B8 1420FFFD */  bnez       $at, .L800010B0_1CB0
    /* 1CBC 800010BC AC40FFFC */   sw        $zero, -0x4($v0)
    /* 1CC0 800010C0 03E00008 */  jr         $ra
    /* 1CC4 800010C4 00000000 */   nop
