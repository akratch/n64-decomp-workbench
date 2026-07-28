glabel menuButton_selectNextOption
    /* BE1FC 8013B00C 27BDFFE0 */  addiu      $sp, $sp, -0x20
    /* BE200 8013B010 AFA60028 */  sw         $a2, 0x28($sp)
    /* BE204 8013B014 00063400 */  sll        $a2, $a2, 16
    /* BE208 8013B018 00063403 */  sra        $a2, $a2, 16
    /* BE20C 8013B01C AFBF0014 */  sw         $ra, 0x14($sp)
    /* BE210 8013B020 00803825 */  or         $a3, $a0, $zero
    /* BE214 8013B024 00001825 */  or         $v1, $zero, $zero
    /* BE218 8013B028 04C10006 */  bgez       $a2, .L8013B044_BE234
    /* BE21C 8013B02C A4A00000 */   sh        $zero, 0x0($a1)
    /* BE220 8013B030 00063023 */  negu       $a2, $a2
    /* BE224 8013B034 00063400 */  sll        $a2, $a2, 16
    /* BE228 8013B038 00063403 */  sra        $a2, $a2, 16
    /* BE22C 8013B03C 10000002 */  b          .L8013B048_BE238
    /* BE230 8013B040 00002825 */   or        $a1, $zero, $zero
  .L8013B044_BE234:
    /* BE234 8013B044 24050001 */  addiu      $a1, $zero, 0x1
  .L8013B048_BE238:
    /* BE238 8013B048 24040800 */  addiu      $a0, $zero, 0x800
    /* BE23C 8013B04C AFA3001C */  sw         $v1, 0x1C($sp)
    /* BE240 8013B050 AFA50018 */  sw         $a1, 0x18($sp)
    /* BE244 8013B054 A7A6002A */  sh         $a2, 0x2A($sp)
    /* BE248 8013B058 0C04DD0B */  jal        moveSelectionCursor
    /* BE24C 8013B05C AFA70020 */   sw        $a3, 0x20($sp)
    /* BE250 8013B060 8FA3001C */  lw         $v1, 0x1C($sp)
    /* BE254 8013B064 8FA50018 */  lw         $a1, 0x18($sp)
    /* BE258 8013B068 87A6002A */  lh         $a2, 0x2A($sp)
    /* BE25C 8013B06C 1040000B */  beqz       $v0, .L8013B09C_BE28C
    /* BE260 8013B070 8FA70020 */   lw        $a3, 0x20($sp)
    /* BE264 8013B074 8CEE0000 */  lw         $t6, 0x0($a3)
    /* BE268 8013B078 25CFFFFF */  addiu      $t7, $t6, -0x1
    /* BE26C 8013B07C 05E10007 */  bgez       $t7, .L8013B09C_BE28C
    /* BE270 8013B080 ACEF0000 */   sw        $t7, 0x0($a3)
    /* BE274 8013B084 10A00004 */  beqz       $a1, .L8013B098_BE288
    /* BE278 8013B088 2403FFFF */   addiu     $v1, $zero, -0x1
    /* BE27C 8013B08C 24D9FFFF */  addiu      $t9, $a2, -0x1
    /* BE280 8013B090 10000002 */  b          .L8013B09C_BE28C
    /* BE284 8013B094 ACF90000 */   sw        $t9, 0x0($a3)
  .L8013B098_BE288:
    /* BE288 8013B098 ACE00000 */  sw         $zero, 0x0($a3)
  .L8013B09C_BE28C:
    /* BE28C 8013B09C 24040400 */  addiu      $a0, $zero, 0x400
    /* BE290 8013B0A0 AFA3001C */  sw         $v1, 0x1C($sp)
    /* BE294 8013B0A4 AFA50018 */  sw         $a1, 0x18($sp)
    /* BE298 8013B0A8 A7A6002A */  sh         $a2, 0x2A($sp)
    /* BE29C 8013B0AC 0C04DD0B */  jal        moveSelectionCursor
    /* BE2A0 8013B0B0 AFA70020 */   sw        $a3, 0x20($sp)
    /* BE2A4 8013B0B4 8FA3001C */  lw         $v1, 0x1C($sp)
    /* BE2A8 8013B0B8 8FA50018 */  lw         $a1, 0x18($sp)
    /* BE2AC 8013B0BC 87A6002A */  lh         $a2, 0x2A($sp)
    /* BE2B0 8013B0C0 1040000C */  beqz       $v0, .L8013B0F4_BE2E4
    /* BE2B4 8013B0C4 8FA70020 */   lw        $a3, 0x20($sp)
    /* BE2B8 8013B0C8 8CE80000 */  lw         $t0, 0x0($a3)
    /* BE2BC 8013B0CC 25090001 */  addiu      $t1, $t0, 0x1
    /* BE2C0 8013B0D0 0126082A */  slt        $at, $t1, $a2
    /* BE2C4 8013B0D4 14200007 */  bnez       $at, .L8013B0F4_BE2E4
    /* BE2C8 8013B0D8 ACE90000 */   sw        $t1, 0x0($a3)
    /* BE2CC 8013B0DC 10A00003 */  beqz       $a1, .L8013B0EC_BE2DC
    /* BE2D0 8013B0E0 24030001 */   addiu     $v1, $zero, 0x1
    /* BE2D4 8013B0E4 10000003 */  b          .L8013B0F4_BE2E4
    /* BE2D8 8013B0E8 ACE00000 */   sw        $zero, 0x0($a3)
  .L8013B0EC_BE2DC:
    /* BE2DC 8013B0EC 24CBFFFF */  addiu      $t3, $a2, -0x1
    /* BE2E0 8013B0F0 ACEB0000 */  sw         $t3, 0x0($a3)
  .L8013B0F4_BE2E4:
    /* BE2E4 8013B0F4 8FBF0014 */  lw         $ra, 0x14($sp)
    /* BE2E8 8013B0F8 27BD0020 */  addiu      $sp, $sp, 0x20
    /* BE2EC 8013B0FC 00601025 */  or         $v0, $v1, $zero
    /* BE2F0 8013B100 03E00008 */  jr         $ra
    /* BE2F4 8013B104 00000000 */   nop
