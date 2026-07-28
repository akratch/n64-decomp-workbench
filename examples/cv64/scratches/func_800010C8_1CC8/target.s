glabel func_800010C8_1CC8
    /* 1CC8 800010C8 3C038034 */  lui        $v1, %hi(D_80341060)
    /* 1CCC 800010CC 3C028034 */  lui        $v0, %hi(objects_array)
    /* 1CD0 800010D0 24422060 */  addiu      $v0, $v0, %lo(objects_array)
    /* 1CD4 800010D4 24631060 */  addiu      $v1, $v1, %lo(D_80341060)
    /* 1CD8 800010D8 8C6E0004 */  lw         $t6, 0x4($v1)
  .L800010DC_1CDC:
    /* 1CDC 800010DC 55C00006 */  bnel       $t6, $zero, .L800010F8_1CF8
    /* 1CE0 800010E0 24630008 */   addiu     $v1, $v1, 0x8
    /* 1CE4 800010E4 AC640004 */  sw         $a0, 0x4($v1)
    /* 1CE8 800010E8 AC600000 */  sw         $zero, 0x0($v1)
    /* 1CEC 800010EC 03E00008 */  jr         $ra
    /* 1CF0 800010F0 00601025 */   or        $v0, $v1, $zero
    /* 1CF4 800010F4 24630008 */  addiu      $v1, $v1, 0x8
  .L800010F8_1CF8:
    /* 1CF8 800010F8 0062082B */  sltu       $at, $v1, $v0
    /* 1CFC 800010FC 5420FFF7 */  bnel       $at, $zero, .L800010DC_1CDC
    /* 1D00 80001100 8C6E0004 */   lw        $t6, 0x4($v1)
    /* 1D04 80001104 00001025 */  or         $v0, $zero, $zero
    /* 1D08 80001108 03E00008 */  jr         $ra
    /* 1D0C 8000110C 00000000 */   nop
