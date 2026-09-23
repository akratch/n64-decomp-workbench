 # Hand-written synthetic listing for pass-order-mini.c; not compiler output.
	.file	1 "pass-order-mini.c"
	.text
	.globl	mini
	.loc	1 9
	.ent	mini 1
mini:
	.frame	$sp, 24, $31
	addiu	$sp, $sp, -24
	sw	$31, 20($sp)
	sw	$16, 16($sp)
	.loc	1 11
	move	$16, $0
	.loc	1 12
	jal	f
	move	$4, $0
	.loc	1 13
	jal	h
	li	$4, 1
	.loc	1 15
	jal	h
	li	$4, 2
	.loc	1 16
	lui	$14, %hi(n)
	lw	$14, %lo(n)($14)
	beq	$14, $0, $L2
	nop
	.loc	1 19
	lui	$3, %hi(arr)
	addiu	$3, $3, %lo(arr)
$L3:
	lw	$15, 0($3)
	lw	$24, x
	addu	$25, $24, $15
	sw	$25, x
	.loc	1 20
	addiu	$16, $16, 1
	addiu	$3, $3, 4
	.loc	1 21
	slti	$1, $16, 8
	bne	$1, $0, $L3
	nop
$L2:
	.loc	1 23
	lw	$31, 20($sp)
	lw	$16, 16($sp)
	jr	$31
	addiu	$sp, $sp, 24
	.end	mini
