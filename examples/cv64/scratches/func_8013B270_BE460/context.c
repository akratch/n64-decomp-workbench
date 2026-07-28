#define _LANGUAGE_C 1
#define F3DEX_GBI_2 1
#define _MIPS_SZLONG 32
#define SCRIPT(...) {}
#define __attribute__(...) 
#define __asm__(...) 
#define M2CTX 1
#define CV64_H 
#define BIT_H 
#define BIT(num) (1 << (num))
#define BITS_MASK(value,mask) ((value) & (mask))
#define BITS_ASSIGN_MASK(value,mask) ((value) &= (mask))
#define BITS_HAS(value,bits) BITS_MASK(value, bits)
#define BITS_NOT_HAS(value,bits) !BITS_HAS(value, bits)
#define BITS_SET(value,bits) ((value) |= (bits))
#define BITS_UNSET(value,bits) ((value) &= ~(bits))
#define BITS_TOGGLE(value,bits) ((value) ^= (bits))
#define MATH_H 
#define _ULTRA64_H_ 
#define _GU_H_ 
#define _MBI_H_ 
#define _SHIFTL(v,s,w) ((unsigned int) (((unsigned int) (v) & ((0x01 << (w)) - 1)) << (s)))
#define _SHIFTR(v,s,w) ((unsigned int) (((unsigned int) (v) >> (s)) & ((0x01 << (w)) - 1)))
#define _SHIFT _SHIFTL
#define G_ON (1)
#define G_OFF (0)
#define _GBI_H_ 
#define _ULTRATYPES_H_ 
#define _SIZE_T 
#define _SIZE_T_DEF 
#define TRUE 1
#define FALSE 0
#define NULL 0
#define F3DEX_GBI 
#define G_NOOP 0x00
#define G_RDPHALF_2 0xf1
#define G_SETOTHERMODE_H 0xe3
#define G_SETOTHERMODE_L 0xe2
#define G_RDPHALF_1 0xe1
#define G_SPNOOP 0xe0
#define G_ENDDL 0xdf
#define G_DL 0xde
#define G_LOAD_UCODE 0xdd
#define G_MOVEMEM 0xdc
#define G_MOVEWORD 0xdb
#define G_MTX 0xda
#define G_GEOMETRYMODE 0xd9
#define G_POPMTX 0xd8
#define G_TEXTURE 0xd7
#define G_DMA_IO 0xd6
#define G_SPECIAL_1 0xd5
#define G_SPECIAL_2 0xd4
#define G_SPECIAL_3 0xd3
#define G_VTX 0x01
#define G_MODIFYVTX 0x02
#define G_CULLDL 0x03
#define G_BRANCH_Z 0x04
#define G_TRI1 0x05
#define G_TRI2 0x06
#define G_QUAD 0x07
#define G_LINE3D 0x08
#define G_SETCIMG 0xff
#define G_SETZIMG 0xfe
#define G_SETTIMG 0xfd
#define G_SETCOMBINE 0xfc
#define G_SETENVCOLOR 0xfb
#define G_SETPRIMCOLOR 0xfa
#define G_SETBLENDCOLOR 0xf9
#define G_SETFOGCOLOR 0xf8
#define G_SETFILLCOLOR 0xf7
#define G_FILLRECT 0xf6
#define G_SETTILE 0xf5
#define G_LOADTILE 0xf4
#define G_LOADBLOCK 0xf3
#define G_SETTILESIZE 0xf2
#define G_LOADTLUT 0xf0
#define G_RDPSETOTHERMODE 0xef
#define G_SETPRIMDEPTH 0xee
#define G_SETSCISSOR 0xed
#define G_SETCONVERT 0xec
#define G_SETKEYR 0xeb
#define G_SETKEYGB 0xea
#define G_RDPFULLSYNC 0xe9
#define G_RDPTILESYNC 0xe8
#define G_RDPPIPESYNC 0xe7
#define G_RDPLOADSYNC 0xe6
#define G_TEXRECTFLIP 0xe5
#define G_TEXRECT 0xe4
#define G_TRI_FILL 0xc8
#define G_TRI_SHADE 0xcc
#define G_TRI_TXTR 0xca
#define G_TRI_SHADE_TXTR 0xce
#define G_TRI_FILL_ZBUFF 0xc9
#define G_TRI_SHADE_ZBUFF 0xcd
#define G_TRI_TXTR_ZBUFF 0xcb
#define G_TRI_SHADE_TXTR_ZBUFF 0xcf
#define G_RDP_TRI_FILL_MASK 0x08
#define G_RDP_TRI_SHADE_MASK 0x04
#define G_RDP_TRI_TXTR_MASK 0x02
#define G_RDP_TRI_ZBUFF_MASK 0x01
#define BOWTIE_VAL 0
#define G_RDP_ADDR_FIXUP 3
#define GDMACMD(x) (x)
#define GIMMCMD(x) (G_IMMFIRST - (x))
#define GRDPCMD(x) (0xff - (x))
#define G_DMACMDSIZ 128
#define G_IMMCMDSIZ 64
#define G_RDPCMDSIZ 64
#define G_TEXTURE_IMAGE_FRAC 2
#define G_TEXTURE_SCALE_FRAC 16
#define G_SCALE_FRAC 8
#define G_ROTATE_FRAC 16
#define G_MAXFBZ 0x3fff
#define GPACK_RGBA5551(r,g,b,a) ((((r) << 8) & 0xf800) | (((g) << 3) & 0x7c0) | (((b) >> 2) & 0x3e) | ((a) & 0x1))
#define GPACK_ZDZ(z,dz) ((z) << 2 | (dz))
#define G_MTX_MODELVIEW 0x00
#define G_MTX_PROJECTION 0x04
#define G_MTX_MUL 0x00
#define G_MTX_LOAD 0x02
#define G_MTX_NOPUSH 0x00
#define G_MTX_PUSH 0x01
#define G_ZBUFFER 0x00000001
#define G_SHADE 0x00000004
#define G_TEXTURE_ENABLE 0x00000000
#define G_SHADING_SMOOTH 0x00200000
#define G_CULL_FRONT 0x00000200
#define G_CULL_BACK 0x00000400
#define G_CULL_BOTH 0x00000600
#define G_FOG 0x00010000
#define G_LIGHTING 0x00020000
#define G_TEXTURE_GEN 0x00040000
#define G_TEXTURE_GEN_LINEAR 0x00080000
#define G_LOD 0x00100000
#define G_CLIPPING 0x00800000
#define G_IM_FMT_RGBA 0
#define G_IM_FMT_YUV 1
#define G_IM_FMT_CI 2
#define G_IM_FMT_IA 3
#define G_IM_FMT_I 4
#define G_IM_SIZ_4b 0
#define G_IM_SIZ_8b 1
#define G_IM_SIZ_16b 2
#define G_IM_SIZ_32b 3
#define G_IM_SIZ_DD 5
#define G_IM_SIZ_4b_BYTES 0
#define G_IM_SIZ_4b_TILE_BYTES G_IM_SIZ_4b_BYTES
#define G_IM_SIZ_4b_LINE_BYTES G_IM_SIZ_4b_BYTES
#define G_IM_SIZ_8b_BYTES 1
#define G_IM_SIZ_8b_TILE_BYTES G_IM_SIZ_8b_BYTES
#define G_IM_SIZ_8b_LINE_BYTES G_IM_SIZ_8b_BYTES
#define G_IM_SIZ_16b_BYTES 2
#define G_IM_SIZ_16b_TILE_BYTES G_IM_SIZ_16b_BYTES
#define G_IM_SIZ_16b_LINE_BYTES G_IM_SIZ_16b_BYTES
#define G_IM_SIZ_32b_BYTES 4
#define G_IM_SIZ_32b_TILE_BYTES 2
#define G_IM_SIZ_32b_LINE_BYTES 2
#define G_IM_SIZ_4b_LOAD_BLOCK G_IM_SIZ_16b
#define G_IM_SIZ_8b_LOAD_BLOCK G_IM_SIZ_16b
#define G_IM_SIZ_16b_LOAD_BLOCK G_IM_SIZ_16b
#define G_IM_SIZ_32b_LOAD_BLOCK G_IM_SIZ_32b
#define G_IM_SIZ_4b_SHIFT 2
#define G_IM_SIZ_8b_SHIFT 1
#define G_IM_SIZ_16b_SHIFT 0
#define G_IM_SIZ_32b_SHIFT 0
#define G_IM_SIZ_4b_INCR 3
#define G_IM_SIZ_8b_INCR 1
#define G_IM_SIZ_16b_INCR 0
#define G_IM_SIZ_32b_INCR 0
#define G_CCMUX_COMBINED 0
#define G_CCMUX_TEXEL0 1
#define G_CCMUX_TEXEL1 2
#define G_CCMUX_PRIMITIVE 3
#define G_CCMUX_SHADE 4
#define G_CCMUX_ENVIRONMENT 5
#define G_CCMUX_CENTER 6
#define G_CCMUX_SCALE 6
#define G_CCMUX_COMBINED_ALPHA 7
#define G_CCMUX_TEXEL0_ALPHA 8
#define G_CCMUX_TEXEL1_ALPHA 9
#define G_CCMUX_PRIMITIVE_ALPHA 10
#define G_CCMUX_SHADE_ALPHA 11
#define G_CCMUX_ENV_ALPHA 12
#define G_CCMUX_LOD_FRACTION 13
#define G_CCMUX_PRIM_LOD_FRAC 14
#define G_CCMUX_NOISE 7
#define G_CCMUX_K4 7
#define G_CCMUX_K5 15
#define G_CCMUX_1 6
#define G_CCMUX_0 31
#define G_ACMUX_COMBINED 0
#define G_ACMUX_TEXEL0 1
#define G_ACMUX_TEXEL1 2
#define G_ACMUX_PRIMITIVE 3
#define G_ACMUX_SHADE 4
#define G_ACMUX_ENVIRONMENT 5
#define G_ACMUX_LOD_FRACTION 0
#define G_ACMUX_PRIM_LOD_FRAC 6
#define G_ACMUX_1 6
#define G_ACMUX_0 7
#define G_CC_PRIMITIVE 0, 0, 0, PRIMITIVE, 0, 0, 0, PRIMITIVE
#define G_CC_SHADE 0, 0, 0, SHADE, 0, 0, 0, SHADE
#define G_CC_MODULATEI TEXEL0, 0, SHADE, 0, 0, 0, 0, SHADE
#define G_CC_MODULATEIA TEXEL0, 0, SHADE, 0, TEXEL0, 0, SHADE, 0
#define G_CC_MODULATEIDECALA TEXEL0, 0, SHADE, 0, 0, 0, 0, TEXEL0
#define G_CC_MODULATERGB G_CC_MODULATEI
#define G_CC_MODULATERGBA G_CC_MODULATEIA
#define G_CC_MODULATERGBDECALA G_CC_MODULATEIDECALA
#define G_CC_MODULATEI_PRIM TEXEL0, 0, PRIMITIVE, 0, 0, 0, 0, PRIMITIVE
#define G_CC_MODULATEIA_PRIM TEXEL0, 0, PRIMITIVE, 0, TEXEL0, 0, PRIMITIVE, 0
#define G_CC_MODULATEIDECALA_PRIM TEXEL0, 0, PRIMITIVE, 0, 0, 0, 0, TEXEL0
#define G_CC_MODULATERGB_PRIM G_CC_MODULATEI_PRIM
#define G_CC_MODULATERGBA_PRIM G_CC_MODULATEIA_PRIM
#define G_CC_MODULATERGBDECALA_PRIM G_CC_MODULATEIDECALA_PRIM
#define G_CC_DECALRGB 0, 0, 0, TEXEL0, 0, 0, 0, SHADE
#define G_CC_DECALRGBA 0, 0, 0, TEXEL0, 0, 0, 0, TEXEL0
#define G_CC_BLENDI ENVIRONMENT, SHADE, TEXEL0, SHADE, 0, 0, 0, SHADE
#define G_CC_BLENDIA ENVIRONMENT, SHADE, TEXEL0, SHADE, TEXEL0, 0, SHADE, 0
#define G_CC_BLENDIDECALA ENVIRONMENT, SHADE, TEXEL0, SHADE, 0, 0, 0, TEXEL0
#define G_CC_BLENDRGBA TEXEL0, SHADE, TEXEL0_ALPHA, SHADE, 0, 0, 0, SHADE
#define G_CC_BLENDRGBDECALA TEXEL0, SHADE, TEXEL0_ALPHA, SHADE, 0, 0, 0, TEXEL0
#define G_CC_ADDRGB 1, 0, TEXEL0, SHADE, 0, 0, 0, SHADE
#define G_CC_ADDRGBDECALA 1, 0, TEXEL0, SHADE, 0, 0, 0, TEXEL0
#define G_CC_REFLECTRGB ENVIRONMENT, 0, TEXEL0, SHADE, 0, 0, 0, SHADE
#define G_CC_REFLECTRGBDECALA ENVIRONMENT, 0, TEXEL0, SHADE, 0, 0, 0, TEXEL0
#define G_CC_HILITERGB PRIMITIVE, SHADE, TEXEL0, SHADE, 0, 0, 0, SHADE
#define G_CC_HILITERGBA PRIMITIVE, SHADE, TEXEL0, SHADE, PRIMITIVE, SHADE, TEXEL0, SHADE
#define G_CC_HILITERGBDECALA PRIMITIVE, SHADE, TEXEL0, SHADE, 0, 0, 0, TEXEL0
#define G_CC_SHADEDECALA 0, 0, 0, SHADE, 0, 0, 0, TEXEL0
#define G_CC_BLENDPE PRIMITIVE, ENVIRONMENT, TEXEL0, ENVIRONMENT, TEXEL0, 0, SHADE, 0
#define G_CC_BLENDPEDECALA PRIMITIVE, ENVIRONMENT, TEXEL0, ENVIRONMENT, 0, 0, 0, TEXEL0
#define _G_CC_BLENDPE ENVIRONMENT, PRIMITIVE, TEXEL0, PRIMITIVE, TEXEL0, 0, SHADE, 0
#define _G_CC_BLENDPEDECALA ENVIRONMENT, PRIMITIVE, TEXEL0, PRIMITIVE, 0, 0, 0, TEXEL0
#define _G_CC_TWOCOLORTEX PRIMITIVE, SHADE, TEXEL0, SHADE, 0, 0, 0, SHADE
#define _G_CC_SPARSEST PRIMITIVE, TEXEL0, LOD_FRACTION, TEXEL0, PRIMITIVE, TEXEL0, LOD_FRACTION, TEXEL0
#define G_CC_TEMPLERP TEXEL1, TEXEL0, PRIM_LOD_FRAC, TEXEL0, TEXEL1, TEXEL0, PRIM_LOD_FRAC, TEXEL0
#define G_CC_TRILERP TEXEL1, TEXEL0, LOD_FRACTION, TEXEL0, TEXEL1, TEXEL0, LOD_FRACTION, TEXEL0
#define G_CC_INTERFERENCE TEXEL0, 0, TEXEL1, 0, TEXEL0, 0, TEXEL1, 0
#define G_CC_1CYUV2RGB TEXEL0, K4, K5, TEXEL0, 0, 0, 0, SHADE
#define G_CC_YUV2RGB TEXEL1, K4, K5, TEXEL1, 0, 0, 0, 0
#define G_CC_PASS2 0, 0, 0, COMBINED, 0, 0, 0, COMBINED
#define G_CC_MODULATEI2 COMBINED, 0, SHADE, 0, 0, 0, 0, SHADE
#define G_CC_MODULATEIA2 COMBINED, 0, SHADE, 0, COMBINED, 0, SHADE, 0
#define G_CC_MODULATERGB2 G_CC_MODULATEI2
#define G_CC_MODULATERGBA2 G_CC_MODULATEIA2
#define G_CC_MODULATEI_PRIM2 COMBINED, 0, PRIMITIVE, 0, 0, 0, 0, PRIMITIVE
#define G_CC_MODULATEIA_PRIM2 COMBINED, 0, PRIMITIVE, 0, COMBINED, 0, PRIMITIVE, 0
#define G_CC_MODULATERGB_PRIM2 G_CC_MODULATEI_PRIM2
#define G_CC_MODULATERGBA_PRIM2 G_CC_MODULATEIA_PRIM2
#define G_CC_DECALRGB2 0, 0, 0, COMBINED, 0, 0, 0, SHADE
#define G_CC_BLENDI2 ENVIRONMENT, SHADE, COMBINED, SHADE, 0, 0, 0, SHADE
#define G_CC_BLENDIA2 ENVIRONMENT, SHADE, COMBINED, SHADE, COMBINED, 0, SHADE, 0
#define G_CC_CHROMA_KEY2 TEXEL0, CENTER, SCALE, 0, 0, 0, 0, 0
#define G_CC_HILITERGB2 ENVIRONMENT, COMBINED, TEXEL0, COMBINED, 0, 0, 0, SHADE
#define G_CC_HILITERGBA2 ENVIRONMENT, COMBINED, TEXEL0, COMBINED, ENVIRONMENT, COMBINED, TEXEL0, COMBINED
#define G_CC_HILITERGBDECALA2 ENVIRONMENT, COMBINED, TEXEL0, COMBINED, 0, 0, 0, TEXEL0
#define G_CC_HILITERGBPASSA2 ENVIRONMENT, COMBINED, TEXEL0, COMBINED, 0, 0, 0, COMBINED
#define G_MDSFT_ALPHACOMPARE 0
#define G_MDSFT_ZSRCSEL 2
#define G_MDSFT_RENDERMODE 3
#define G_MDSFT_BLENDER 16
#define G_MDSFT_BLENDMASK 0
#define G_MDSFT_ALPHADITHER 4
#define G_MDSFT_RGBDITHER 6
#define G_MDSFT_COMBKEY 8
#define G_MDSFT_TEXTCONV 9
#define G_MDSFT_TEXTFILT 12
#define G_MDSFT_TEXTLUT 14
#define G_MDSFT_TEXTLOD 16
#define G_MDSFT_TEXTDETAIL 17
#define G_MDSFT_TEXTPERSP 19
#define G_MDSFT_CYCLETYPE 20
#define G_MDSFT_COLORDITHER 22
#define G_MDSFT_PIPELINE 23
#define G_PM_1PRIMITIVE (1 << G_MDSFT_PIPELINE)
#define G_PM_NPRIMITIVE (0 << G_MDSFT_PIPELINE)
#define G_CYC_1CYCLE (0 << G_MDSFT_CYCLETYPE)
#define G_CYC_2CYCLE (1 << G_MDSFT_CYCLETYPE)
#define G_CYC_COPY (2 << G_MDSFT_CYCLETYPE)
#define G_CYC_FILL (3 << G_MDSFT_CYCLETYPE)
#define G_TP_NONE (0 << G_MDSFT_TEXTPERSP)
#define G_TP_PERSP (1 << G_MDSFT_TEXTPERSP)
#define G_TD_CLAMP (0 << G_MDSFT_TEXTDETAIL)
#define G_TD_SHARPEN (1 << G_MDSFT_TEXTDETAIL)
#define G_TD_DETAIL (2 << G_MDSFT_TEXTDETAIL)
#define G_TL_TILE (0 << G_MDSFT_TEXTLOD)
#define G_TL_LOD (1 << G_MDSFT_TEXTLOD)
#define G_TT_NONE (0 << G_MDSFT_TEXTLUT)
#define G_TT_RGBA16 (2 << G_MDSFT_TEXTLUT)
#define G_TT_IA16 (3 << G_MDSFT_TEXTLUT)
#define G_TF_POINT (0 << G_MDSFT_TEXTFILT)
#define G_TF_AVERAGE (3 << G_MDSFT_TEXTFILT)
#define G_TF_BILERP (2 << G_MDSFT_TEXTFILT)
#define G_TC_CONV (0 << G_MDSFT_TEXTCONV)
#define G_TC_FILTCONV (5 << G_MDSFT_TEXTCONV)
#define G_TC_FILT (6 << G_MDSFT_TEXTCONV)
#define G_CK_NONE (0 << G_MDSFT_COMBKEY)
#define G_CK_KEY (1 << G_MDSFT_COMBKEY)
#define G_CD_MAGICSQ (0 << G_MDSFT_RGBDITHER)
#define G_CD_BAYER (1 << G_MDSFT_RGBDITHER)
#define G_CD_NOISE (2 << G_MDSFT_RGBDITHER)
#define G_CD_DISABLE (3 << G_MDSFT_RGBDITHER)
#define G_CD_ENABLE G_CD_NOISE
#define G_AD_PATTERN (0 << G_MDSFT_ALPHADITHER)
#define G_AD_NOTPATTERN (1 << G_MDSFT_ALPHADITHER)
#define G_AD_NOISE (2 << G_MDSFT_ALPHADITHER)
#define G_AD_DISABLE (3 << G_MDSFT_ALPHADITHER)
#define G_AC_NONE (0 << G_MDSFT_ALPHACOMPARE)
#define G_AC_THRESHOLD (1 << G_MDSFT_ALPHACOMPARE)
#define G_AC_DITHER (3 << G_MDSFT_ALPHACOMPARE)
#define G_ZS_PIXEL (0 << G_MDSFT_ZSRCSEL)
#define G_ZS_PRIM (1 << G_MDSFT_ZSRCSEL)
#define AA_EN 0x8
#define Z_CMP 0x10
#define Z_UPD 0x20
#define IM_RD 0x40
#define CLR_ON_CVG 0x80
#define CVG_DST_CLAMP 0
#define CVG_DST_WRAP 0x100
#define CVG_DST_FULL 0x200
#define CVG_DST_SAVE 0x300
#define ZMODE_OPA 0
#define ZMODE_INTER 0x400
#define ZMODE_XLU 0x800
#define ZMODE_DEC 0xc00
#define CVG_X_ALPHA 0x1000
#define ALPHA_CVG_SEL 0x2000
#define FORCE_BL 0x4000
#define TEX_EDGE 0x0000
#define G_BL_CLR_IN 0
#define G_BL_CLR_MEM 1
#define G_BL_CLR_BL 2
#define G_BL_CLR_FOG 3
#define G_BL_1MA 0
#define G_BL_A_MEM 1
#define G_BL_A_IN 0
#define G_BL_A_FOG 1
#define G_BL_A_SHADE 2
#define G_BL_1 2
#define G_BL_0 3
#define GBL_c1(m1a,m1b,m2a,m2b) (m1a) << 30 | (m1b) << 26 | (m2a) << 22 | (m2b) << 18
#define GBL_c2(m1a,m1b,m2a,m2b) (m1a) << 28 | (m1b) << 24 | (m2a) << 20 | (m2b) << 16
#define RM_AA_ZB_OPA_SURF(clk) AA_EN | Z_CMP | Z_UPD | IM_RD | CVG_DST_CLAMP | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_RA_ZB_OPA_SURF(clk) AA_EN | Z_CMP | Z_UPD | CVG_DST_CLAMP | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_AA_ZB_XLU_SURF(clk) AA_EN | Z_CMP | IM_RD | CVG_DST_WRAP | CLR_ON_CVG | FORCE_BL | ZMODE_XLU | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_ZB_OPA_DECAL(clk) AA_EN | Z_CMP | IM_RD | CVG_DST_WRAP | ALPHA_CVG_SEL | ZMODE_DEC | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_RA_ZB_OPA_DECAL(clk) AA_EN | Z_CMP | CVG_DST_WRAP | ALPHA_CVG_SEL | ZMODE_DEC | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_AA_ZB_XLU_DECAL(clk) AA_EN | Z_CMP | IM_RD | CVG_DST_WRAP | CLR_ON_CVG | FORCE_BL | ZMODE_DEC | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_ZB_OPA_INTER(clk) AA_EN | Z_CMP | Z_UPD | IM_RD | CVG_DST_CLAMP | ALPHA_CVG_SEL | ZMODE_INTER | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_RA_ZB_OPA_INTER(clk) AA_EN | Z_CMP | Z_UPD | CVG_DST_CLAMP | ALPHA_CVG_SEL | ZMODE_INTER | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_AA_ZB_XLU_INTER(clk) AA_EN | Z_CMP | IM_RD | CVG_DST_WRAP | CLR_ON_CVG | FORCE_BL | ZMODE_INTER | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_ZB_XLU_LINE(clk) AA_EN | Z_CMP | IM_RD | CVG_DST_CLAMP | CVG_X_ALPHA | ALPHA_CVG_SEL | FORCE_BL | ZMODE_XLU | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_ZB_DEC_LINE(clk) AA_EN | Z_CMP | IM_RD | CVG_DST_SAVE | CVG_X_ALPHA | ALPHA_CVG_SEL | FORCE_BL | ZMODE_DEC | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_ZB_TEX_EDGE(clk) AA_EN | Z_CMP | Z_UPD | IM_RD | CVG_DST_CLAMP | CVG_X_ALPHA | ALPHA_CVG_SEL | ZMODE_OPA | TEX_EDGE | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_AA_ZB_TEX_INTER(clk) AA_EN | Z_CMP | Z_UPD | IM_RD | CVG_DST_CLAMP | CVG_X_ALPHA | ALPHA_CVG_SEL | ZMODE_INTER | TEX_EDGE | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_AA_ZB_SUB_SURF(clk) AA_EN | Z_CMP | Z_UPD | IM_RD | CVG_DST_FULL | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_AA_ZB_PCL_SURF(clk) AA_EN | Z_CMP | Z_UPD | IM_RD | CVG_DST_CLAMP | ZMODE_OPA | G_AC_DITHER | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_ZB_OPA_TERR(clk) AA_EN | Z_CMP | Z_UPD | IM_RD | CVG_DST_CLAMP | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_ZB_TEX_TERR(clk) AA_EN | Z_CMP | Z_UPD | IM_RD | CVG_DST_CLAMP | CVG_X_ALPHA | ALPHA_CVG_SEL | ZMODE_OPA | TEX_EDGE | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_ZB_SUB_TERR(clk) AA_EN | Z_CMP | Z_UPD | IM_RD | CVG_DST_FULL | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_OPA_SURF(clk) AA_EN | IM_RD | CVG_DST_CLAMP | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_RA_OPA_SURF(clk) AA_EN | CVG_DST_CLAMP | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_AA_XLU_SURF(clk) AA_EN | IM_RD | CVG_DST_WRAP | CLR_ON_CVG | FORCE_BL | ZMODE_OPA | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_XLU_LINE(clk) AA_EN | IM_RD | CVG_DST_CLAMP | CVG_X_ALPHA | ALPHA_CVG_SEL | FORCE_BL | ZMODE_OPA | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_DEC_LINE(clk) AA_EN | IM_RD | CVG_DST_FULL | CVG_X_ALPHA | ALPHA_CVG_SEL | FORCE_BL | ZMODE_OPA | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_TEX_EDGE(clk) AA_EN | IM_RD | CVG_DST_CLAMP | CVG_X_ALPHA | ALPHA_CVG_SEL | ZMODE_OPA | TEX_EDGE | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_AA_SUB_SURF(clk) AA_EN | IM_RD | CVG_DST_FULL | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_AA_PCL_SURF(clk) AA_EN | IM_RD | CVG_DST_CLAMP | ZMODE_OPA | G_AC_DITHER | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_OPA_TERR(clk) AA_EN | IM_RD | CVG_DST_CLAMP | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_TEX_TERR(clk) AA_EN | IM_RD | CVG_DST_CLAMP | CVG_X_ALPHA | ALPHA_CVG_SEL | ZMODE_OPA | TEX_EDGE | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_AA_SUB_TERR(clk) AA_EN | IM_RD | CVG_DST_FULL | ZMODE_OPA | ALPHA_CVG_SEL | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_ZB_OPA_SURF(clk) Z_CMP | Z_UPD | CVG_DST_FULL | ALPHA_CVG_SEL | ZMODE_OPA | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_ZB_XLU_SURF(clk) Z_CMP | IM_RD | CVG_DST_FULL | FORCE_BL | ZMODE_XLU | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_ZB_OPA_DECAL(clk) Z_CMP | CVG_DST_FULL | ALPHA_CVG_SEL | ZMODE_DEC | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_A_MEM)
#define RM_ZB_XLU_DECAL(clk) Z_CMP | IM_RD | CVG_DST_FULL | FORCE_BL | ZMODE_DEC | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_ZB_CLD_SURF(clk) Z_CMP | IM_RD | CVG_DST_SAVE | FORCE_BL | ZMODE_XLU | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_ZB_OVL_SURF(clk) Z_CMP | IM_RD | CVG_DST_SAVE | FORCE_BL | ZMODE_DEC | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_ZB_PCL_SURF(clk) Z_CMP | Z_UPD | CVG_DST_FULL | ZMODE_OPA | G_AC_DITHER | GBL_c##clk(G_BL_CLR_IN, G_BL_0, G_BL_CLR_IN, G_BL_1)
#define RM_OPA_SURF(clk) CVG_DST_CLAMP | FORCE_BL | ZMODE_OPA | GBL_c##clk(G_BL_CLR_IN, G_BL_0, G_BL_CLR_IN, G_BL_1)
#define RM_XLU_SURF(clk) IM_RD | CVG_DST_FULL | FORCE_BL | ZMODE_OPA | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_TEX_EDGE(clk) CVG_DST_CLAMP | CVG_X_ALPHA | ALPHA_CVG_SEL | FORCE_BL | ZMODE_OPA | TEX_EDGE | AA_EN | GBL_c##clk(G_BL_CLR_IN, G_BL_0, G_BL_CLR_IN, G_BL_1)
#define RM_CLD_SURF(clk) IM_RD | CVG_DST_SAVE | FORCE_BL | ZMODE_OPA | GBL_c##clk(G_BL_CLR_IN, G_BL_A_IN, G_BL_CLR_MEM, G_BL_1MA)
#define RM_PCL_SURF(clk) CVG_DST_FULL | FORCE_BL | ZMODE_OPA | G_AC_DITHER | GBL_c##clk(G_BL_CLR_IN, G_BL_0, G_BL_CLR_IN, G_BL_1)
#define RM_ADD(clk) IM_RD | CVG_DST_SAVE | FORCE_BL | ZMODE_OPA | GBL_c##clk(G_BL_CLR_IN, G_BL_A_FOG, G_BL_CLR_MEM, G_BL_1)
#define RM_NOOP(clk) GBL_c##clk(0, 0, 0, 0)
#define RM_VISCVG(clk) IM_RD | FORCE_BL | GBL_c##clk(G_BL_CLR_IN, G_BL_0, G_BL_CLR_BL, G_BL_A_MEM)
#define RM_OPA_CI(clk) CVG_DST_CLAMP | ZMODE_OPA | GBL_c##clk(G_BL_CLR_IN, G_BL_0, G_BL_CLR_IN, G_BL_1)
#define G_RM_AA_ZB_OPA_SURF RM_AA_ZB_OPA_SURF(1)
#define G_RM_AA_ZB_OPA_SURF2 RM_AA_ZB_OPA_SURF(2)
#define G_RM_AA_ZB_XLU_SURF RM_AA_ZB_XLU_SURF(1)
#define G_RM_AA_ZB_XLU_SURF2 RM_AA_ZB_XLU_SURF(2)
#define G_RM_AA_ZB_OPA_DECAL RM_AA_ZB_OPA_DECAL(1)
#define G_RM_AA_ZB_OPA_DECAL2 RM_AA_ZB_OPA_DECAL(2)
#define G_RM_AA_ZB_XLU_DECAL RM_AA_ZB_XLU_DECAL(1)
#define G_RM_AA_ZB_XLU_DECAL2 RM_AA_ZB_XLU_DECAL(2)
#define G_RM_AA_ZB_OPA_INTER RM_AA_ZB_OPA_INTER(1)
#define G_RM_AA_ZB_OPA_INTER2 RM_AA_ZB_OPA_INTER(2)
#define G_RM_AA_ZB_XLU_INTER RM_AA_ZB_XLU_INTER(1)
#define G_RM_AA_ZB_XLU_INTER2 RM_AA_ZB_XLU_INTER(2)
#define G_RM_AA_ZB_XLU_LINE RM_AA_ZB_XLU_LINE(1)
#define G_RM_AA_ZB_XLU_LINE2 RM_AA_ZB_XLU_LINE(2)
#define G_RM_AA_ZB_DEC_LINE RM_AA_ZB_DEC_LINE(1)
#define G_RM_AA_ZB_DEC_LINE2 RM_AA_ZB_DEC_LINE(2)
#define G_RM_AA_ZB_TEX_EDGE RM_AA_ZB_TEX_EDGE(1)
#define G_RM_AA_ZB_TEX_EDGE2 RM_AA_ZB_TEX_EDGE(2)
#define G_RM_AA_ZB_TEX_INTER RM_AA_ZB_TEX_INTER(1)
#define G_RM_AA_ZB_TEX_INTER2 RM_AA_ZB_TEX_INTER(2)
#define G_RM_AA_ZB_SUB_SURF RM_AA_ZB_SUB_SURF(1)
#define G_RM_AA_ZB_SUB_SURF2 RM_AA_ZB_SUB_SURF(2)
#define G_RM_AA_ZB_PCL_SURF RM_AA_ZB_PCL_SURF(1)
#define G_RM_AA_ZB_PCL_SURF2 RM_AA_ZB_PCL_SURF(2)
#define G_RM_AA_ZB_OPA_TERR RM_AA_ZB_OPA_TERR(1)
#define G_RM_AA_ZB_OPA_TERR2 RM_AA_ZB_OPA_TERR(2)
#define G_RM_AA_ZB_TEX_TERR RM_AA_ZB_TEX_TERR(1)
#define G_RM_AA_ZB_TEX_TERR2 RM_AA_ZB_TEX_TERR(2)
#define G_RM_AA_ZB_SUB_TERR RM_AA_ZB_SUB_TERR(1)
#define G_RM_AA_ZB_SUB_TERR2 RM_AA_ZB_SUB_TERR(2)
#define G_RM_RA_ZB_OPA_SURF RM_RA_ZB_OPA_SURF(1)
#define G_RM_RA_ZB_OPA_SURF2 RM_RA_ZB_OPA_SURF(2)
#define G_RM_RA_ZB_OPA_DECAL RM_RA_ZB_OPA_DECAL(1)
#define G_RM_RA_ZB_OPA_DECAL2 RM_RA_ZB_OPA_DECAL(2)
#define G_RM_RA_ZB_OPA_INTER RM_RA_ZB_OPA_INTER(1)
#define G_RM_RA_ZB_OPA_INTER2 RM_RA_ZB_OPA_INTER(2)
#define G_RM_AA_OPA_SURF RM_AA_OPA_SURF(1)
#define G_RM_AA_OPA_SURF2 RM_AA_OPA_SURF(2)
#define G_RM_AA_XLU_SURF RM_AA_XLU_SURF(1)
#define G_RM_AA_XLU_SURF2 RM_AA_XLU_SURF(2)
#define G_RM_AA_XLU_LINE RM_AA_XLU_LINE(1)
#define G_RM_AA_XLU_LINE2 RM_AA_XLU_LINE(2)
#define G_RM_AA_DEC_LINE RM_AA_DEC_LINE(1)
#define G_RM_AA_DEC_LINE2 RM_AA_DEC_LINE(2)
#define G_RM_AA_TEX_EDGE RM_AA_TEX_EDGE(1)
#define G_RM_AA_TEX_EDGE2 RM_AA_TEX_EDGE(2)
#define G_RM_AA_SUB_SURF RM_AA_SUB_SURF(1)
#define G_RM_AA_SUB_SURF2 RM_AA_SUB_SURF(2)
#define G_RM_AA_PCL_SURF RM_AA_PCL_SURF(1)
#define G_RM_AA_PCL_SURF2 RM_AA_PCL_SURF(2)
#define G_RM_AA_OPA_TERR RM_AA_OPA_TERR(1)
#define G_RM_AA_OPA_TERR2 RM_AA_OPA_TERR(2)
#define G_RM_AA_TEX_TERR RM_AA_TEX_TERR(1)
#define G_RM_AA_TEX_TERR2 RM_AA_TEX_TERR(2)
#define G_RM_AA_SUB_TERR RM_AA_SUB_TERR(1)
#define G_RM_AA_SUB_TERR2 RM_AA_SUB_TERR(2)
#define G_RM_RA_OPA_SURF RM_RA_OPA_SURF(1)
#define G_RM_RA_OPA_SURF2 RM_RA_OPA_SURF(2)
#define G_RM_ZB_OPA_SURF RM_ZB_OPA_SURF(1)
#define G_RM_ZB_OPA_SURF2 RM_ZB_OPA_SURF(2)
#define G_RM_ZB_XLU_SURF RM_ZB_XLU_SURF(1)
#define G_RM_ZB_XLU_SURF2 RM_ZB_XLU_SURF(2)
#define G_RM_ZB_OPA_DECAL RM_ZB_OPA_DECAL(1)
#define G_RM_ZB_OPA_DECAL2 RM_ZB_OPA_DECAL(2)
#define G_RM_ZB_XLU_DECAL RM_ZB_XLU_DECAL(1)
#define G_RM_ZB_XLU_DECAL2 RM_ZB_XLU_DECAL(2)
#define G_RM_ZB_CLD_SURF RM_ZB_CLD_SURF(1)
#define G_RM_ZB_CLD_SURF2 RM_ZB_CLD_SURF(2)
#define G_RM_ZB_OVL_SURF RM_ZB_OVL_SURF(1)
#define G_RM_ZB_OVL_SURF2 RM_ZB_OVL_SURF(2)
#define G_RM_ZB_PCL_SURF RM_ZB_PCL_SURF(1)
#define G_RM_ZB_PCL_SURF2 RM_ZB_PCL_SURF(2)
#define G_RM_OPA_SURF RM_OPA_SURF(1)
#define G_RM_OPA_SURF2 RM_OPA_SURF(2)
#define G_RM_XLU_SURF RM_XLU_SURF(1)
#define G_RM_XLU_SURF2 RM_XLU_SURF(2)
#define G_RM_CLD_SURF RM_CLD_SURF(1)
#define G_RM_CLD_SURF2 RM_CLD_SURF(2)
#define G_RM_TEX_EDGE RM_TEX_EDGE(1)
#define G_RM_TEX_EDGE2 RM_TEX_EDGE(2)
#define G_RM_PCL_SURF RM_PCL_SURF(1)
#define G_RM_PCL_SURF2 RM_PCL_SURF(2)
#define G_RM_ADD RM_ADD(1)
#define G_RM_ADD2 RM_ADD(2)
#define G_RM_NOOP RM_NOOP(1)
#define G_RM_NOOP2 RM_NOOP(2)
#define G_RM_VISCVG RM_VISCVG(1)
#define G_RM_VISCVG2 RM_VISCVG(2)
#define G_RM_OPA_CI RM_OPA_CI(1)
#define G_RM_OPA_CI2 RM_OPA_CI(2)
#define G_RM_FOG_SHADE_A GBL_c1(G_BL_CLR_FOG, G_BL_A_SHADE, G_BL_CLR_IN, G_BL_1MA)
#define G_RM_FOG_PRIM_A GBL_c1(G_BL_CLR_FOG, G_BL_A_FOG, G_BL_CLR_IN, G_BL_1MA)
#define G_RM_PASS GBL_c1(G_BL_CLR_IN, G_BL_0, G_BL_CLR_IN, G_BL_1)
#define G_CV_K0 175
#define G_CV_K1 -43
#define G_CV_K2 -89
#define G_CV_K3 222
#define G_CV_K4 114
#define G_CV_K5 42
#define G_SC_NON_INTERLACE 0
#define G_SC_ODD_INTERLACE 3
#define G_SC_EVEN_INTERLACE 2
#define G_DL_PUSH 0x00
#define G_DL_NOPUSH 0x01
#define G_MAXZ 0x03ff
#define G_MV_MMTX 2
#define G_MV_PMTX 6
#define G_MV_VIEWPORT 8
#define G_MV_LIGHT 10
#define G_MV_POINT 12
#define G_MV_MATRIX 14
#define G_MVO_LOOKATX (0 * 24)
#define G_MVO_LOOKATY (1 * 24)
#define G_MVO_L0 (2 * 24)
#define G_MVO_L1 (3 * 24)
#define G_MVO_L2 (4 * 24)
#define G_MVO_L3 (5 * 24)
#define G_MVO_L4 (6 * 24)
#define G_MVO_L5 (7 * 24)
#define G_MVO_L6 (8 * 24)
#define G_MVO_L7 (9 * 24)
#define G_MW_MATRIX 0x00
#define G_MW_NUMLIGHT 0x02
#define G_MW_CLIP 0x04
#define G_MW_SEGMENT 0x06
#define G_MW_FOG 0x08
#define G_MW_LIGHTCOL 0x0a
#define G_MW_FORCEMTX 0x0c
#define G_MW_PERSPNORM 0x0e
#define G_MWO_NUMLIGHT 0x00
#define G_MWO_CLIP_RNX 0x04
#define G_MWO_CLIP_RNY 0x0c
#define G_MWO_CLIP_RPX 0x14
#define G_MWO_CLIP_RPY 0x1c
#define G_MWO_SEGMENT_0 0x00
#define G_MWO_SEGMENT_1 0x01
#define G_MWO_SEGMENT_2 0x02
#define G_MWO_SEGMENT_3 0x03
#define G_MWO_SEGMENT_4 0x04
#define G_MWO_SEGMENT_5 0x05
#define G_MWO_SEGMENT_6 0x06
#define G_MWO_SEGMENT_7 0x07
#define G_MWO_SEGMENT_8 0x08
#define G_MWO_SEGMENT_9 0x09
#define G_MWO_SEGMENT_A 0x0a
#define G_MWO_SEGMENT_B 0x0b
#define G_MWO_SEGMENT_C 0x0c
#define G_MWO_SEGMENT_D 0x0d
#define G_MWO_SEGMENT_E 0x0e
#define G_MWO_SEGMENT_F 0x0f
#define G_MWO_FOG 0x00
#define G_MWO_aLIGHT_1 0x00
#define G_MWO_bLIGHT_1 0x04
#define G_MWO_aLIGHT_2 0x18
#define G_MWO_bLIGHT_2 0x1c
#define G_MWO_aLIGHT_3 0x30
#define G_MWO_bLIGHT_3 0x34
#define G_MWO_aLIGHT_4 0x48
#define G_MWO_bLIGHT_4 0x4c
#define G_MWO_aLIGHT_5 0x60
#define G_MWO_bLIGHT_5 0x64
#define G_MWO_aLIGHT_6 0x78
#define G_MWO_bLIGHT_6 0x7c
#define G_MWO_aLIGHT_7 0x90
#define G_MWO_bLIGHT_7 0x94
#define G_MWO_aLIGHT_8 0xa8
#define G_MWO_bLIGHT_8 0xac
#define G_MWO_MATRIX_XX_XY_I 0x00
#define G_MWO_MATRIX_XZ_XW_I 0x04
#define G_MWO_MATRIX_YX_YY_I 0x08
#define G_MWO_MATRIX_YZ_YW_I 0x0c
#define G_MWO_MATRIX_ZX_ZY_I 0x10
#define G_MWO_MATRIX_ZZ_ZW_I 0x14
#define G_MWO_MATRIX_WX_WY_I 0x18
#define G_MWO_MATRIX_WZ_WW_I 0x1c
#define G_MWO_MATRIX_XX_XY_F 0x20
#define G_MWO_MATRIX_XZ_XW_F 0x24
#define G_MWO_MATRIX_YX_YY_F 0x28
#define G_MWO_MATRIX_YZ_YW_F 0x2c
#define G_MWO_MATRIX_ZX_ZY_F 0x30
#define G_MWO_MATRIX_ZZ_ZW_F 0x34
#define G_MWO_MATRIX_WX_WY_F 0x38
#define G_MWO_MATRIX_WZ_WW_F 0x3c
#define G_MWO_POINT_RGBA 0x10
#define G_MWO_POINT_ST 0x14
#define G_MWO_POINT_XYSCREEN 0x18
#define G_MWO_POINT_ZSCREEN 0x1c
#define gdSPDefLights0(ar,ag,ab) { {{{ar, ag, ab}, 0, {ar, ag, ab}, 0}}, { { { {0, 0, 0}, 0, {0, 0, 0}, 0, {0, 0, 0}, 0 } } } }
#define gdSPDefLights1(ar,ag,ab,r1,g1,b1,x1,y1,z1) { {{{ar, ag, ab}, 0, {ar, ag, ab}, 0}}, { { { {r1, g1, b1}, 0, {r1, g1, b1}, 0, {x1, y1, z1}, 0 } } } }
#define gdSPDefLights2(ar,ag,ab,r1,g1,b1,x1,y1,z1,r2,g2,b2,x2,y2,z2) { {{{ar, ag, ab}, 0, {ar, ag, ab}, 0}}, { {{{r1, g1, b1}, 0, {r1, g1, b1}, 0, {x1, y1, z1}, 0}}, { { {r2, g2, b2}, 0, {r2, g2, b2}, 0, {x2, y2, z2}, 0 } } } }
#define gdSPDefLights3(ar,ag,ab,r1,g1,b1,x1,y1,z1,r2,g2,b2,x2,y2,z2,r3,g3,b3,x3,y3,z3) { {{{ar, ag, ab}, 0, {ar, ag, ab}, 0}}, { {{{r1, g1, b1}, 0, {r1, g1, b1}, 0, {x1, y1, z1}, 0}}, {{{r2, g2, b2}, 0, {r2, g2, b2}, 0, {x2, y2, z2}, 0}}, { { {r3, g3, b3}, 0, {r3, g3, b3}, 0, {x3, y3, z3}, 0 } } } }
#define gdSPDefLights4(ar,ag,ab,r1,g1,b1,x1,y1,z1,r2,g2,b2,x2,y2,z2,r3,g3,b3,x3,y3,z3,r4,g4,b4,x4,y4,z4) { {{{ar, ag, ab}, 0, {ar, ag, ab}, 0}}, { {{{r1, g1, b1}, 0, {r1, g1, b1}, 0, {x1, y1, z1}, 0}}, {{{r2, g2, b2}, 0, {r2, g2, b2}, 0, {x2, y2, z2}, 0}}, {{{r3, g3, b3}, 0, {r3, g3, b3}, 0, {x3, y3, z3}, 0}}, { { {r4, g4, b4}, 0, {r4, g4, b4}, 0, {x4, y4, z4}, 0 } } } }
#define gdSPDefLights5(ar,ag,ab,r1,g1,b1,x1,y1,z1,r2,g2,b2,x2,y2,z2,r3,g3,b3,x3,y3,z3,r4,g4,b4,x4,y4,z4,r5,g5,b5,x5,y5,z5) { {{{ar, ag, ab}, 0, {ar, ag, ab}, 0}}, { {{{r1, g1, b1}, 0, {r1, g1, b1}, 0, {x1, y1, z1}, 0}}, {{{r2, g2, b2}, 0, {r2, g2, b2}, 0, {x2, y2, z2}, 0}}, {{{r3, g3, b3}, 0, {r3, g3, b3}, 0, {x3, y3, z3}, 0}}, {{{r4, g4, b4}, 0, {r4, g4, b4}, 0, {x4, y4, z4}, 0}}, { { {r5, g5, b5}, 0, {r5, g5, b5}, 0, {x5, y5, z5}, 0 } } } }
#define gdSPDefLights6(ar,ag,ab,r1,g1,b1,x1,y1,z1,r2,g2,b2,x2,y2,z2,r3,g3,b3,x3,y3,z3,r4,g4,b4,x4,y4,z4,r5,g5,b5,x5,y5,z5,r6,g6,b6,x6,y6,z6) { {{{ar, ag, ab}, 0, {ar, ag, ab}, 0}}, { {{{r1, g1, b1}, 0, {r1, g1, b1}, 0, {x1, y1, z1}, 0}}, {{{r2, g2, b2}, 0, {r2, g2, b2}, 0, {x2, y2, z2}, 0}}, {{{r3, g3, b3}, 0, {r3, g3, b3}, 0, {x3, y3, z3}, 0}}, {{{r4, g4, b4}, 0, {r4, g4, b4}, 0, {x4, y4, z4}, 0}}, {{{r5, g5, b5}, 0, {r5, g5, b5}, 0, {x5, y5, z5}, 0}}, { { {r6, g6, b6}, 0, {r6, g6, b6}, 0, {x6, y6, z6}, 0 } } } }
#define gdSPDefLights7(ar,ag,ab,r1,g1,b1,x1,y1,z1,r2,g2,b2,x2,y2,z2,r3,g3,b3,x3,y3,z3,r4,g4,b4,x4,y4,z4,r5,g5,b5,x5,y5,z5,r6,g6,b6,x6,y6,z6,r7,g7,b7,x7,y7,z7) { {{{ar, ag, ab}, 0, {ar, ag, ab}, 0}}, { {{{r1, g1, b1}, 0, {r1, g1, b1}, 0, {x1, y1, z1}, 0}}, {{{r2, g2, b2}, 0, {r2, g2, b2}, 0, {x2, y2, z2}, 0}}, {{{r3, g3, b3}, 0, {r3, g3, b3}, 0, {x3, y3, z3}, 0}}, {{{r4, g4, b4}, 0, {r4, g4, b4}, 0, {x4, y4, z4}, 0}}, {{{r5, g5, b5}, 0, {r5, g5, b5}, 0, {x5, y5, z5}, 0}}, {{{r6, g6, b6}, 0, {r6, g6, b6}, 0, {x6, y6, z6}, 0}}, { { {r7, g7, b7}, 0, {r7, g7, b7}, 0, {x7, y7, z7}, 0 } } } }
#define gdSPDefLookAt(rightx,righty,rightz,upx,upy,upz) { { {{{0, 0, 0}, 0, {0, 0, 0}, 0, {rightx, righty, rightz}, 0}}, { { {0, 0x80, 0}, 0, {0, 0x80, 0}, 0, {upx, upy, upz}, 0 } } } }
#define MakeTexRect(xh,yh,flip,tile,xl,yl,s,t,dsdx,dtdy) G_TEXRECT, xh, yh, 0, flip, 0, tile, xl, yl, s, t, dsdx, dtdy
#define gDma0p(pkt,c,s,l) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL((c), 24, 8) | _SHIFTL((l), 0, 24); _g->words.w1 = (unsigned int) (s); }
#define gsDma0p(c,s,l) { { _SHIFTL((c), 24, 8) | _SHIFTL((l), 0, 24), (unsigned int) (s) } }
#define gDma1p(pkt,c,s,l,p) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL((c), 24, 8) | _SHIFTL((p), 16, 8) | _SHIFTL((l), 0, 16)); _g->words.w1 = (unsigned int) (s); }
#define gsDma1p(c,s,l,p) { { (_SHIFTL((c), 24, 8) | _SHIFTL((p), 16, 8) | _SHIFTL((l), 0, 16)), (unsigned int) (s) } }
#define gDma2p(pkt,c,adrs,len,idx,ofs) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL((c), 24, 8) | _SHIFTL(((len) -1) / 8, 19, 5) | _SHIFTL((ofs) / 8, 8, 8) | _SHIFTL((idx), 0, 8)); _g->words.w1 = (unsigned int) (adrs); }
#define gsDma2p(c,adrs,len,idx,ofs) { { (_SHIFTL((c), 24, 8) | _SHIFTL(((len) -1) / 8, 19, 5) | _SHIFTL((ofs) / 8, 8, 8) | _SHIFTL((idx), 0, 8)), (unsigned int) (adrs) } }
#define gSPNoOp(pkt) gDma0p(pkt, G_SPNOOP, 0, 0)
#define gsSPNoOp() gsDma0p(G_SPNOOP, 0, 0)
#define gSPMatrix(pkt,m,p) gDma2p((pkt), G_MTX, (m), sizeof(Mtx), (p) ^ G_MTX_PUSH, 0)
#define gsSPMatrix(m,p) gsDma2p(G_MTX, (m), sizeof(Mtx), (p) ^ G_MTX_PUSH, 0)
#define gSPVertex(pkt,v,n,v0) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_VTX, 24, 8) | _SHIFTL((n), 12, 8) | _SHIFTL((v0) + (n), 1, 7); _g->words.w1 = (unsigned int) (v); }
#define gsSPVertex(v,n,v0) { { (_SHIFTL(G_VTX, 24, 8) | _SHIFTL((n), 12, 8) | _SHIFTL((v0) + (n), 1, 7)), (unsigned int) (v) } }
#define gSPViewport(pkt,v) gDma2p((pkt), G_MOVEMEM, (v), sizeof(Vp), G_MV_VIEWPORT, 0)
#define gsSPViewport(v) gsDma2p(G_MOVEMEM, (v), sizeof(Vp), G_MV_VIEWPORT, 0)
#define gSPDisplayList(pkt,dl) gDma1p(pkt, G_DL, dl, 0, G_DL_PUSH)
#define gsSPDisplayList(dl) gsDma1p(G_DL, dl, 0, G_DL_PUSH)
#define gSPBranchList(pkt,dl) gDma1p(pkt, G_DL, dl, 0, G_DL_NOPUSH)
#define gsSPBranchList(dl) gsDma1p(G_DL, dl, 0, G_DL_NOPUSH)
#define gSPSprite2DBase(pkt,s) gDma1p(pkt, G_SPRITE2D_BASE, s, sizeof(uSprite), 0)
#define gsSPSprite2DBase(s) gsDma1p(G_SPRITE2D_BASE, s, sizeof(uSprite), 0)
#define gImmp0(pkt,c) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL((c), 24, 8); }
#define gsImmp0(c) { { _SHIFTL((c), 24, 8) } }
#define gImmp1(pkt,c,p0) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL((c), 24, 8); _g->words.w1 = (unsigned int) (p0); }
#define gsImmp1(c,p0) { { _SHIFTL((c), 24, 8), (unsigned int) (p0) } }
#define gImmp2(pkt,c,p0,p1) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL((c), 24, 8); _g->words.w1 = _SHIFTL((p0), 16, 16) | _SHIFTL((p1), 8, 8); }
#define gsImmp2(c,p0,p1) { { _SHIFTL((c), 24, 8), _SHIFTL((p0), 16, 16) | _SHIFTL((p1), 8, 8) } }
#define gImmp3(pkt,c,p0,p1,p2) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL((c), 24, 8); _g->words.w1 = (_SHIFTL((p0), 16, 16) | _SHIFTL((p1), 8, 8) | _SHIFTL((p2), 0, 8)); }
#define gsImmp3(c,p0,p1,p2) { { _SHIFTL((c), 24, 8), (_SHIFTL((p0), 16, 16) | _SHIFTL((p1), 8, 8) | _SHIFTL((p2), 0, 8)) } }
#define gImmp21(pkt,c,p0,p1,dat) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL((c), 24, 8) | _SHIFTL((p0), 8, 16) | _SHIFTL((p1), 0, 8)); _g->words.w1 = (unsigned int) (dat); }
#define gsImmp21(c,p0,p1,dat) { { _SHIFTL((c), 24, 8) | _SHIFTL((p0), 8, 16) | _SHIFTL((p1), 0, 8), (unsigned int) (dat) } }
#define gMoveWd(pkt,index,offset,data) gDma1p((pkt), G_MOVEWORD, data, offset, index)
#define gsMoveWd(index,offset,data) gsDma1p(G_MOVEWORD, data, offset, index)
#define gSPSprite2DScaleFlip(pkt,sx,sy,fx,fy) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_SPRITE2D_SCALEFLIP, 24, 8) | _SHIFTL((fx), 8, 8) | _SHIFTL((fy), 0, 8)); _g->words.w1 = (_SHIFTL((sx), 16, 16) | _SHIFTL((sy), 0, 16)); }
#define gsSPSprite2DScaleFlip(sx,sy,fx,fy) { { (_SHIFTL(G_SPRITE2D_SCALEFLIP, 24, 8) | _SHIFTL((fx), 8, 8) | _SHIFTL((fy), 0, 8)), (_SHIFTL((sx), 16, 16) | _SHIFTL((sy), 0, 16)) } }
#define gSPSprite2DDraw(pkt,px,py) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_SPRITE2D_DRAW, 24, 8)); _g->words.w1 = (_SHIFTL((px), 16, 16) | _SHIFTL((py), 0, 16)); }
#define gsSPSprite2DDraw(px,py) { { (_SHIFTL(G_SPRITE2D_DRAW, 24, 8)), (_SHIFTL((px), 16, 16) | _SHIFTL((py), 0, 16)) } }
#define __gsSP1Triangle_w1(v0,v1,v2) (_SHIFTL((v0) * 2, 16, 8) | _SHIFTL((v1) * 2, 8, 8) | _SHIFTL((v2) * 2, 0, 8))
#define __gsSP1Triangle_w1f(v0,v1,v2,flag) (((flag) == 0) ? __gsSP1Triangle_w1(v0, v1, v2) : ((flag) == 1) ? __gsSP1Triangle_w1(v1, v2, v0) : __gsSP1Triangle_w1(v2, v0, v1))
#define __gsSPLine3D_w1(v0,v1,wd) (_SHIFTL((v0) * 2, 16, 8) | _SHIFT((v1) * 2, 8, 8) | _SHIFT((wd), 0, 8))
#define __gsSPLine3D_w1f(v0,v1,wd,flag) (((flag) == 0) ? __gsSPLine3D_w1(v0, v1, wd) : __gsSPLine3D_w1(v1, v0, wd))
#define __gsSP1Quadrangle_w1f(v0,v1,v2,v3,flag) (((flag) == 0) ? __gsSP1Triangle_w1(v0, v1, v2) : ((flag) == 1) ? __gsSP1Triangle_w1(v1, v2, v3) : ((flag) == 2) ? __gsSP1Triangle_w1(v2, v3, v0) : __gsSP1Triangle_w1(v3, v0, v1))
#define __gsSP1Quadrangle_w2f(v0,v1,v2,v3,flag) (((flag) == 0) ? __gsSP1Triangle_w1(v0, v2, v3) : ((flag) == 1) ? __gsSP1Triangle_w1(v1, v3, v0) : ((flag) == 2) ? __gsSP1Triangle_w1(v2, v0, v1) : __gsSP1Triangle_w1(v3, v1, v2))
#define gSP1Triangle(pkt,v0,v1,v2,flag) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_TRI1, 24, 8) | __gsSP1Triangle_w1f(v0, v1, v2, flag); _g->words.w1 = 0; }
#define gsSP1Triangle(v0,v1,v2,flag) { { _SHIFTL(G_TRI1, 24, 8) | __gsSP1Triangle_w1f(v0, v1, v2, flag), 0 } }
#define gSPLine3D(pkt,v0,v1,flag) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_LINE3D, 24, 8) | __gsSPLine3D_w1f(v0, v1, 0, flag); _g->words.w1 = 0; }
#define gsSPLine3D(v0,v1,flag) { { _SHIFTL(G_LINE3D, 24, 8) | __gsSPLine3D_w1f(v0, v1, 0, flag), 0 } }
#define gSPLineW3D(pkt,v0,v1,wd,flag) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_LINE3D, 24, 8) | __gsSPLine3D_w1f(v0, v1, wd, flag); _g->words.w1 = 0; }
#define gsSPLineW3D(v0,v1,wd,flag) { { _SHIFTL(G_LINE3D, 24, 8) | __gsSPLine3D_w1f(v0, v1, wd, flag), 0 } }
#define gSP1Quadrangle(pkt,v0,v1,v2,v3,flag) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_QUAD, 24, 8) | __gsSP1Quadrangle_w1f(v0, v1, v2, v3, flag)); _g->words.w1 = __gsSP1Quadrangle_w2f(v0, v1, v2, v3, flag); }
#define gsSP1Quadrangle(v0,v1,v2,v3,flag) { { (_SHIFTL(G_QUAD, 24, 8) | __gsSP1Quadrangle_w1f(v0, v1, v2, v3, flag)), __gsSP1Quadrangle_w2f(v0, v1, v2, v3, flag) } }
#define gSP2Triangles(pkt,v00,v01,v02,flag0,v10,v11,v12,flag1) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_TRI2, 24, 8) | __gsSP1Triangle_w1f(v00, v01, v02, flag0)); _g->words.w1 = __gsSP1Triangle_w1f(v10, v11, v12, flag1); }
#define gsSP2Triangles(v00,v01,v02,flag0,v10,v11,v12,flag1) { { (_SHIFTL(G_TRI2, 24, 8) | __gsSP1Triangle_w1f(v00, v01, v02, flag0)), __gsSP1Triangle_w1f(v10, v11, v12, flag1) } }
#define gSPCullDisplayList(pkt,vstart,vend) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_CULLDL, 24, 8) | _SHIFTL((vstart) * 2, 0, 16); _g->words.w1 = _SHIFTL((vend) * 2, 0, 16); }
#define gsSPCullDisplayList(vstart,vend) { { _SHIFTL(G_CULLDL, 24, 8) | _SHIFTL((vstart) * 2, 0, 16), _SHIFTL((vend) * 2, 0, 16) } }
#define gSPSegment(pkt,segment,base) gMoveWd(pkt, G_MW_SEGMENT, (segment) * 4, base)
#define gsSPSegment(segment,base) gsMoveWd(G_MW_SEGMENT, (segment) * 4, base)
#define FR_NEG_FRUSTRATIO_1 0x00000001
#define FR_POS_FRUSTRATIO_1 0x0000ffff
#define FR_NEG_FRUSTRATIO_2 0x00000002
#define FR_POS_FRUSTRATIO_2 0x0000fffe
#define FR_NEG_FRUSTRATIO_3 0x00000003
#define FR_POS_FRUSTRATIO_3 0x0000fffd
#define FR_NEG_FRUSTRATIO_4 0x00000004
#define FR_POS_FRUSTRATIO_4 0x0000fffc
#define FR_NEG_FRUSTRATIO_5 0x00000005
#define FR_POS_FRUSTRATIO_5 0x0000fffb
#define FR_NEG_FRUSTRATIO_6 0x00000006
#define FR_POS_FRUSTRATIO_6 0x0000fffa
#define gSPClipRatio(pkt,r) { gMoveWd(pkt, G_MW_CLIP, G_MWO_CLIP_RNX, FR_NEG_##r); gMoveWd(pkt, G_MW_CLIP, G_MWO_CLIP_RNY, FR_NEG_##r); gMoveWd(pkt, G_MW_CLIP, G_MWO_CLIP_RPX, FR_POS_##r); gMoveWd(pkt, G_MW_CLIP, G_MWO_CLIP_RPY, FR_POS_##r); }
#define gsSPClipRatio(r) gsMoveWd(G_MW_CLIP, G_MWO_CLIP_RNX, FR_NEG_##r), gsMoveWd(G_MW_CLIP, G_MWO_CLIP_RNY, FR_NEG_##r), gsMoveWd(G_MW_CLIP, G_MWO_CLIP_RPX, FR_POS_##r), gsMoveWd(G_MW_CLIP, G_MWO_CLIP_RPY, FR_POS_##r)
#define gSPInsertMatrix(pkt,where,num) ERROR !!gSPInsertMatrix is no longer supported.
#define gsSPInsertMatrix(where,num) ERROR !!gsSPInsertMatrix is no longer supported.
#define gSPForceMatrix(pkt,mptr) { gDma2p((pkt), G_MOVEMEM, (mptr), sizeof(Mtx), G_MV_MATRIX, 0); gMoveWd((pkt), G_MW_FORCEMTX, 0, 0x00010000); }
#define gsSPForceMatrix(mptr) gsDma2p(G_MOVEMEM, (mptr), sizeof(Mtx), G_MV_MATRIX, 0), gsMoveWd(G_MW_FORCEMTX, 0, 0x00010000)
#define gSPModifyVertex(pkt,vtx,where,val) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_MODIFYVTX, 24, 8) | _SHIFTL((where), 16, 8) | _SHIFTL((vtx) * 2, 0, 16)); _g->words.w1 = (unsigned int) (val); }
#define gsSPModifyVertex(vtx,where,val) { { _SHIFTL(G_MODIFYVTX, 24, 8) | _SHIFTL((where), 16, 8) | _SHIFTL((vtx) * 2, 0, 16), (unsigned int) (val) } }
#define G_BZ_PERSP 0
#define G_BZ_ORTHO 1
#define G_DEPTOZSrg(zval,near,far,flag,zmin,zmax) (((unsigned int) FTOFIX32( ((flag) == G_BZ_PERSP ? (1.0f - (float) (near) / (float) (zval)) / (1.0f - (float) (near) / (float) (far)) : ((float) (zval) - (float) (near)) / ((float) (far) - (float) (near))))) * (((int) ((zmax) - (zmin))) & ~1) + (int) FTOFIX32(zmin))
#define G_DEPTOZS(zval,near,far,flag) G_DEPTOZSrg(zval, near, far, flag, 0, G_MAXZ)
#define gSPBranchLessZrg(pkt,dl,vtx,zval,near,far,flag,zmin,zmax) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_RDPHALF_1, 24, 8); _g->words.w1 = (unsigned int) (dl); _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_BRANCH_Z, 24, 8) | _SHIFTL((vtx) * 5, 12, 12) | _SHIFTL((vtx) * 2, 0, 12)); _g->words.w1 = G_DEPTOZSrg(zval, near, far, flag, zmin, zmax); }
#define gsSPBranchLessZrg(dl,vtx,zval,near,far,flag,zmin,zmax) {{ _SHIFTL(G_RDPHALF_1, 24, 8), (unsigned int) (dl), }}, { { _SHIFTL(G_BRANCH_Z, 24, 8) | _SHIFTL((vtx) * 5, 12, 12) | _SHIFTL((vtx) * 2, 0, 12), G_DEPTOZSrg(zval, near, far, flag, zmin, zmax), } }
#define gSPBranchLessZ(pkt,dl,vtx,zval,near,far,flag) gSPBranchLessZrg(pkt, dl, vtx, zval, near, far, flag, 0, G_MAXZ)
#define gsSPBranchLessZ(dl,vtx,zval,near,far,flag) gsSPBranchLessZrg(dl, vtx, zval, near, far, flag, 0, G_MAXZ)
#define gSPBranchLessZraw(pkt,dl,vtx,zval) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_RDPHALF_1, 24, 8); _g->words.w1 = (unsigned int) (dl); _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_BRANCH_Z, 24, 8) | _SHIFTL((vtx) * 5, 12, 12) | _SHIFTL((vtx) * 2, 0, 12)); _g->words.w1 = (unsigned int) (zval); }
#define gsSPBranchLessZraw(dl,vtx,zval) {{ _SHIFTL(G_RDPHALF_1, 24, 8), (unsigned int) (dl), }}, { { _SHIFTL(G_BRANCH_Z, 24, 8) | _SHIFTL((vtx) * 5, 12, 12) | _SHIFTL((vtx) * 2, 0, 12), (unsigned int) (zval), } }
#define gSPLoadUcodeEx(pkt,uc_start,uc_dstart,uc_dsize) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_RDPHALF_1, 24, 8); _g->words.w1 = (unsigned int) (uc_dstart); _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_LOAD_UCODE, 24, 8) | _SHIFTL((int) (uc_dsize) -1, 0, 16)); _g->words.w1 = (unsigned int) (uc_start); }
#define gsSPLoadUcodeEx(uc_start,uc_dstart,uc_dsize) {{ _SHIFTL(G_RDPHALF_1, 24, 8), (unsigned int) (uc_dstart), }}, { { _SHIFTL(G_LOAD_UCODE, 24, 8) | _SHIFTL((int) (uc_dsize) -1, 0, 16), (unsigned int) (uc_start), } }
#define gSPLoadUcode(pkt,uc_start,uc_dstart) gSPLoadUcodeEx((pkt), (uc_start), (uc_dstart), SP_UCODE_DATA_SIZE)
#define gsSPLoadUcode(uc_start,uc_dstart) gsSPLoadUcodeEx((uc_start), (uc_dstart), SP_UCODE_DATA_SIZE)
#define gSPLoadUcodeL(pkt,ucode) gSPLoadUcode((pkt), OS_K0_TO_PHYSICAL(&##ucode##TextStart), OS_K0_TO_PHYSICAL(&##ucode##DataStart))
#define gsSPLoadUcodeL(ucode) gsSPLoadUcode(OS_K0_TO_PHYSICAL(&##ucode##TextStart), OS_K0_TO_PHYSICAL(&##ucode##DataStart))
#define gSPDma_io(pkt,flag,dmem,dram,size) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_DMA_IO, 24, 8) | _SHIFTL((flag), 23, 1) | _SHIFTL((dmem) / 8, 13, 10) | _SHIFTL((size) -1, 0, 12); _g->words.w1 = (unsigned int) (dram); }
#define gsSPDma_io(flag,dmem,dram,size) { { _SHIFTL(G_DMA_IO, 24, 8) | _SHIFTL((flag), 23, 1) | _SHIFTL((dmem) / 8, 13, 10) | _SHIFTL((size) -1, 0, 12), (unsigned int) (dram) } }
#define gSPDmaRead(pkt,dmem,dram,size) gSPDma_io((pkt), 0, (dmem), (dram), (size))
#define gsSPDmaRead(dmem,dram,size) gsSPDma_io(0, (dmem), (dram), (size))
#define gSPDmaWrite(pkt,dmem,dram,size) gSPDma_io((pkt), 1, (dmem), (dram), (size))
#define gsSPDmaWrite(dmem,dram,size) gsSPDma_io(1, (dmem), (dram), (size))
#define NUML(n) ((n) * 24)
#define NUMLIGHTS_0 1
#define NUMLIGHTS_1 1
#define NUMLIGHTS_2 2
#define NUMLIGHTS_3 3
#define NUMLIGHTS_4 4
#define NUMLIGHTS_5 5
#define NUMLIGHTS_6 6
#define NUMLIGHTS_7 7
#define gSPNumLights(pkt,n) gMoveWd(pkt, G_MW_NUMLIGHT, G_MWO_NUMLIGHT, NUML(n))
#define gsSPNumLights(n) gsMoveWd(G_MW_NUMLIGHT, G_MWO_NUMLIGHT, NUML(n))
#define LIGHT_1 1
#define LIGHT_2 2
#define LIGHT_3 3
#define LIGHT_4 4
#define LIGHT_5 5
#define LIGHT_6 6
#define LIGHT_7 7
#define LIGHT_8 8
#define gSPLight(pkt,l,n) gDma2p((pkt), G_MOVEMEM, (l), sizeof(Light), G_MV_LIGHT, (n) * 24 + 24)
#define gsSPLight(l,n) gsDma2p(G_MOVEMEM, (l), sizeof(Light), G_MV_LIGHT, (n) * 24 + 24)
#define gSPLightColor(pkt,n,col) { gMoveWd(pkt, G_MW_LIGHTCOL, G_MWO_a##n, col); gMoveWd(pkt, G_MW_LIGHTCOL, G_MWO_b##n, col); }
#define gsSPLightColor(n,col) gsMoveWd(G_MW_LIGHTCOL, G_MWO_a##n, col), gsMoveWd(G_MW_LIGHTCOL, G_MWO_b##n, col)
#define gSPSetLights0(pkt,name) { gSPNumLights(pkt, NUMLIGHTS_0); gSPLight(pkt, &name.l[0], 1); gSPLight(pkt, &name.a, 2); }
#define gsSPSetLights0(name) gsSPNumLights(NUMLIGHTS_0), gsSPLight(&name.l[0], 1), gsSPLight(&name.a, 2)
#define gSPSetLights1(pkt,name) { gSPNumLights(pkt, NUMLIGHTS_1); gSPLight(pkt, &name.l[0], 1); gSPLight(pkt, &name.a, 2); }
#define gsSPSetLights1(name) gsSPNumLights(NUMLIGHTS_1), gsSPLight(&name.l[0], 1), gsSPLight(&name.a, 2)
#define gSPSetLights2(pkt,name) { gSPNumLights(pkt, NUMLIGHTS_2); gSPLight(pkt, &name.l[0], 1); gSPLight(pkt, &name.l[1], 2); gSPLight(pkt, &name.a, 3); }
#define gsSPSetLights2(name) gsSPNumLights(NUMLIGHTS_2), gsSPLight(&name.l[0], 1), gsSPLight(&name.l[1], 2), gsSPLight(&name.a, 3)
#define gSPSetLights3(pkt,name) { gSPNumLights(pkt, NUMLIGHTS_3); gSPLight(pkt, &name.l[0], 1); gSPLight(pkt, &name.l[1], 2); gSPLight(pkt, &name.l[2], 3); gSPLight(pkt, &name.a, 4); }
#define gsSPSetLights3(name) gsSPNumLights(NUMLIGHTS_3), gsSPLight(&name.l[0], 1), gsSPLight(&name.l[1], 2), gsSPLight(&name.l[2], 3), gsSPLight(&name.a, 4)
#define gSPSetLights4(pkt,name) { gSPNumLights(pkt, NUMLIGHTS_4); gSPLight(pkt, &name.l[0], 1); gSPLight(pkt, &name.l[1], 2); gSPLight(pkt, &name.l[2], 3); gSPLight(pkt, &name.l[3], 4); gSPLight(pkt, &name.a, 5); }
#define gsSPSetLights4(name) gsSPNumLights(NUMLIGHTS_4), gsSPLight(&name.l[0], 1), gsSPLight(&name.l[1], 2), gsSPLight(&name.l[2], 3), gsSPLight(&name.l[3], 4), gsSPLight(&name.a, 5)
#define gSPSetLights5(pkt,name) { gSPNumLights(pkt, NUMLIGHTS_5); gSPLight(pkt, &name.l[0], 1); gSPLight(pkt, &name.l[1], 2); gSPLight(pkt, &name.l[2], 3); gSPLight(pkt, &name.l[3], 4); gSPLight(pkt, &name.l[4], 5); gSPLight(pkt, &name.a, 6); }
#define gsSPSetLights5(name) gsSPNumLights(NUMLIGHTS_5), gsSPLight(&name.l[0], 1), gsSPLight(&name.l[1], 2), gsSPLight(&name.l[2], 3), gsSPLight(&name.l[3], 4), gsSPLight(&name.l[4], 5), gsSPLight(&name.a, 6)
#define gSPSetLights6(pkt,name) { gSPNumLights(pkt, NUMLIGHTS_6); gSPLight(pkt, &name.l[0], 1); gSPLight(pkt, &name.l[1], 2); gSPLight(pkt, &name.l[2], 3); gSPLight(pkt, &name.l[3], 4); gSPLight(pkt, &name.l[4], 5); gSPLight(pkt, &name.l[5], 6); gSPLight(pkt, &name.a, 7); }
#define gsSPSetLights6(name) gsSPNumLights(NUMLIGHTS_6), gsSPLight(&name.l[0], 1), gsSPLight(&name.l[1], 2), gsSPLight(&name.l[2], 3), gsSPLight(&name.l[3], 4), gsSPLight(&name.l[4], 5), gsSPLight(&name.l[5], 6), gsSPLight(&name.a, 7)
#define gSPSetLights7(pkt,name) { gSPNumLights(pkt, NUMLIGHTS_7); gSPLight(pkt, &name.l[0], 1); gSPLight(pkt, &name.l[1], 2); gSPLight(pkt, &name.l[2], 3); gSPLight(pkt, &name.l[3], 4); gSPLight(pkt, &name.l[4], 5); gSPLight(pkt, &name.l[5], 6); gSPLight(pkt, &name.l[6], 7); gSPLight(pkt, &name.a, 8); }
#define gsSPSetLights7(name) gsSPNumLights(NUMLIGHTS_7), gsSPLight(&name.l[0], 1), gsSPLight(&name.l[1], 2), gsSPLight(&name.l[2], 3), gsSPLight(&name.l[3], 4), gsSPLight(&name.l[4], 5), gsSPLight(&name.l[5], 6), gsSPLight(&name.l[6], 7), gsSPLight(&name.a, 8)
#define gSPLookAtX(pkt,l) gDma2p((pkt), G_MOVEMEM, (l), sizeof(Light), G_MV_LIGHT, G_MVO_LOOKATX)
#define gsSPLookAtX(l) gsDma2p(G_MOVEMEM, (l), sizeof(Light), G_MV_LIGHT, G_MVO_LOOKATX)
#define gSPLookAtY(pkt,l) gDma2p((pkt), G_MOVEMEM, (l), sizeof(Light), G_MV_LIGHT, G_MVO_LOOKATY)
#define gsSPLookAtY(l) gsDma2p(G_MOVEMEM, (l), sizeof(Light), G_MV_LIGHT, G_MVO_LOOKATY)
#define gSPLookAt(pkt,la) { gSPLookAtX(pkt, la) gSPLookAtY(pkt, (char*) (la) + 16) }
#define gsSPLookAt(la) gsSPLookAtX(la), gsSPLookAtY((char*) (la) + 16)
#define gDPSetHilite1Tile(pkt,tile,hilite,width,height) gDPSetTileSize(pkt, tile, (hilite)->h.x1 & 0xfff, (hilite)->h.y1 & 0xfff, ((((width) -1) * 4) + (hilite)->h.x1) & 0xfff, ((((height) -1) * 4) + (hilite)->h.y1) & 0xfff)
#define gDPSetHilite2Tile(pkt,tile,hilite,width,height) gDPSetTileSize(pkt, tile, (hilite)->h.x2 & 0xfff, (hilite)->h.y2 & 0xfff, ((((width) -1) * 4) + (hilite)->h.x2) & 0xfff, ((((height) -1) * 4) + (hilite)->h.y2) & 0xfff)
#define gSPFogFactor(pkt,fm,fo) gMoveWd(pkt, G_MW_FOG, G_MWO_FOG, (_SHIFTL(fm, 16, 16) | _SHIFTL(fo, 0, 16)))
#define gsSPFogFactor(fm,fo) gsMoveWd(G_MW_FOG, G_MWO_FOG, (_SHIFTL(fm, 16, 16) | _SHIFTL(fo, 0, 16)))
#define gSPFogPosition(pkt,min,max) gMoveWd(pkt, G_MW_FOG, G_MWO_FOG, (_SHIFTL((128000 / ((max) - (min))), 16, 16) | _SHIFTL(((500 - (min)) * 256 / ((max) - (min))), 0, 16)))
#define gsSPFogPosition(min,max) gsMoveWd(G_MW_FOG, G_MWO_FOG, (_SHIFTL((128000 / ((max) - (min))), 16, 16) | _SHIFTL(((500 - (min)) * 256 / ((max) - (min))), 0, 16)))
#define gSPTexture(pkt,s,t,level,tile,on) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_TEXTURE, 24, 8) | _SHIFTL(BOWTIE_VAL, 16, 8) | _SHIFTL((level), 11, 3) | _SHIFTL((tile), 8, 3) | _SHIFTL((on), 1, 7)); _g->words.w1 = (_SHIFTL((s), 16, 16) | _SHIFTL((t), 0, 16)); }
#define gsSPTexture(s,t,level,tile,on) { { (_SHIFTL(G_TEXTURE, 24, 8) | _SHIFTL(BOWTIE_VAL, 16, 8) | _SHIFTL((level), 11, 3) | _SHIFTL((tile), 8, 3) | _SHIFTL((on), 1, 7)), (_SHIFTL((s), 16, 16) | _SHIFTL((t), 0, 16)) } }
#define gSPTextureL(pkt,s,t,level,xparam,tile,on) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_TEXTURE, 24, 8) | _SHIFTL((xparam), 16, 8) | _SHIFTL((level), 11, 3) | _SHIFTL((tile), 8, 3) | _SHIFTL((on), 1, 7)); _g->words.w1 = (_SHIFTL((s), 16, 16) | _SHIFTL((t), 0, 16)); }
#define gsSPTextureL(s,t,level,xparam,tile,on) { { (_SHIFTL(G_TEXTURE, 24, 8) | _SHIFTL((xparam), 16, 8) | _SHIFTL((level), 11, 3) | _SHIFTL((tile), 8, 3) | _SHIFTL((on), 1, 7)), (_SHIFTL((s), 16, 16) | _SHIFTL((t), 0, 16)) } }
#define gSPPerspNormalize(pkt,s) gMoveWd(pkt, G_MW_PERSPNORM, 0, (s))
#define gsSPPerspNormalize(s) gsMoveWd(G_MW_PERSPNORM, 0, (s))
#define gSPPopMatrixN(pkt,n,num) gDma2p((pkt), G_POPMTX, (num) * 64, 64, 2, 0)
#define gsSPPopMatrixN(n,num) gsDma2p(G_POPMTX, (num) * 64, 64, 2, 0)
#define gSPPopMatrix(pkt,n) gSPPopMatrixN((pkt), (n), 1)
#define gsSPPopMatrix(n) gsSPPopMatrixN((n), 1)
#define gSPEndDisplayList(pkt) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_ENDDL, 24, 8); _g->words.w1 = 0; }
#define gsSPEndDisplayList() { { _SHIFTL(G_ENDDL, 24, 8), 0 } }
#define gSPGeometryMode(pkt,c,s) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_GEOMETRYMODE, 24, 8) | _SHIFTL(~(u32) (c), 0, 24); _g->words.w1 = (u32) (s); }
#define gsSPGeometryMode(c,s) { { (_SHIFTL(G_GEOMETRYMODE, 24, 8) | _SHIFTL(~(u32) (c), 0, 24)), (u32) (s) } }
#define gSPSetGeometryMode(pkt,word) gSPGeometryMode((pkt), 0, (word))
#define gsSPSetGeometryMode(word) gsSPGeometryMode(0, (word))
#define gSPClearGeometryMode(pkt,word) gSPGeometryMode((pkt), (word), 0)
#define gsSPClearGeometryMode(word) gsSPGeometryMode((word), 0)
#define gSPLoadGeometryMode(pkt,word) gSPGeometryMode((pkt), -1, (word))
#define gsSPLoadGeometryMode(word) gsSPGeometryMode(-1, (word))
#define gSPSetOtherMode(pkt,cmd,sft,len,data) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(cmd, 24, 8) | _SHIFTL(32 - (sft) - (len), 8, 8) | _SHIFTL((len) -1, 0, 8)); _g->words.w1 = (unsigned int) (data); }
#define gsSPSetOtherMode(cmd,sft,len,data) { { _SHIFTL(cmd, 24, 8) | _SHIFTL(32 - (sft) - (len), 8, 8) | _SHIFTL((len) -1, 0, 8), (unsigned int) (data) } }
#define gDPPipelineMode(pkt,mode) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_PIPELINE, 1, mode)
#define gsDPPipelineMode(mode) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_PIPELINE, 1, mode)
#define gDPSetCycleType(pkt,type) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_CYCLETYPE, 2, type)
#define gsDPSetCycleType(type) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_CYCLETYPE, 2, type)
#define gDPSetTexturePersp(pkt,type) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_TEXTPERSP, 1, type)
#define gsDPSetTexturePersp(type) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_TEXTPERSP, 1, type)
#define gDPSetTextureDetail(pkt,type) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_TEXTDETAIL, 2, type)
#define gsDPSetTextureDetail(type) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_TEXTDETAIL, 2, type)
#define gDPSetTextureLOD(pkt,type) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_TEXTLOD, 1, type)
#define gsDPSetTextureLOD(type) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_TEXTLOD, 1, type)
#define gDPSetTextureLUT(pkt,type) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_TEXTLUT, 2, type)
#define gsDPSetTextureLUT(type) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_TEXTLUT, 2, type)
#define gDPSetTextureFilter(pkt,type) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_TEXTFILT, 2, type)
#define gsDPSetTextureFilter(type) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_TEXTFILT, 2, type)
#define gDPSetTextureConvert(pkt,type) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_TEXTCONV, 3, type)
#define gsDPSetTextureConvert(type) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_TEXTCONV, 3, type)
#define gDPSetCombineKey(pkt,type) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_COMBKEY, 1, type)
#define gsDPSetCombineKey(type) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_COMBKEY, 1, type)
#define gDPSetColorDither(pkt,mode) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_RGBDITHER, 2, mode)
#define gsDPSetColorDither(mode) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_RGBDITHER, 2, mode)
#define gDPSetAlphaDither(pkt,mode) gSPSetOtherMode(pkt, G_SETOTHERMODE_H, G_MDSFT_ALPHADITHER, 2, mode)
#define gsDPSetAlphaDither(mode) gsSPSetOtherMode(G_SETOTHERMODE_H, G_MDSFT_ALPHADITHER, 2, mode)
#define gDPSetBlendMask(pkt,mask) gDPNoOp(pkt)
#define gsDPSetBlendMask(mask) gsDPNoOp()
#define gDPSetAlphaCompare(pkt,type) gSPSetOtherMode(pkt, G_SETOTHERMODE_L, G_MDSFT_ALPHACOMPARE, 2, type)
#define gsDPSetAlphaCompare(type) gsSPSetOtherMode(G_SETOTHERMODE_L, G_MDSFT_ALPHACOMPARE, 2, type)
#define gDPSetDepthSource(pkt,src) gSPSetOtherMode(pkt, G_SETOTHERMODE_L, G_MDSFT_ZSRCSEL, 1, src)
#define gsDPSetDepthSource(src) gsSPSetOtherMode(G_SETOTHERMODE_L, G_MDSFT_ZSRCSEL, 1, src)
#define gDPSetRenderMode(pkt,c0,c1) gSPSetOtherMode(pkt, G_SETOTHERMODE_L, G_MDSFT_RENDERMODE, 29, (c0) | (c1))
#define gsDPSetRenderMode(c0,c1) gsSPSetOtherMode(G_SETOTHERMODE_L, G_MDSFT_RENDERMODE, 29, (c0) | (c1))
#define gSetImage(pkt,cmd,fmt,siz,width,i) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(cmd, 24, 8) | _SHIFTL(fmt, 21, 3) | _SHIFTL(siz, 19, 2) | _SHIFTL((width) -1, 0, 12); _g->words.w1 = (unsigned int) (i); }
#define gsSetImage(cmd,fmt,siz,width,i) { { _SHIFTL(cmd, 24, 8) | _SHIFTL(fmt, 21, 3) | _SHIFTL(siz, 19, 2) | _SHIFTL((width) -1, 0, 12), (unsigned int) (i) } }
#define gDPSetColorImage(pkt,f,s,w,i) gSetImage(pkt, G_SETCIMG, f, s, w, i)
#define gsDPSetColorImage(f,s,w,i) gsSetImage(G_SETCIMG, f, s, w, i)
#define gDPSetDepthImage(pkt,i) gSetImage(pkt, G_SETZIMG, 0, 0, 1, i)
#define gsDPSetDepthImage(i) gsSetImage(G_SETZIMG, 0, 0, 1, i)
#define gDPSetMaskImage(pkt,i) gDPSetDepthImage(pkt, i)
#define gsDPSetMaskImage(i) gsDPSetDepthImage(i)
#define gDPSetTextureImage(pkt,f,s,w,i) gSetImage(pkt, G_SETTIMG, f, s, w, i)
#define gsDPSetTextureImage(f,s,w,i) gsSetImage(G_SETTIMG, f, s, w, i)
#define gDPSetCombine(pkt,muxs0,muxs1) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_SETCOMBINE, 24, 8) | _SHIFTL(muxs0, 0, 24); _g->words.w1 = (unsigned int) (muxs1); }
#define gsDPSetCombine(muxs0,muxs1) { { _SHIFTL(G_SETCOMBINE, 24, 8) | _SHIFTL(muxs0, 0, 24), (unsigned int) (muxs1) } }
#define GCCc0w0(saRGB0,mRGB0,saA0,mA0) (_SHIFTL((saRGB0), 20, 4) | _SHIFTL((mRGB0), 15, 5) | _SHIFTL((saA0), 12, 3) | _SHIFTL((mA0), 9, 3))
#define GCCc1w0(saRGB1,mRGB1) (_SHIFTL((saRGB1), 5, 4) | _SHIFTL((mRGB1), 0, 5))
#define GCCc0w1(sbRGB0,aRGB0,sbA0,aA0) (_SHIFTL((sbRGB0), 28, 4) | _SHIFTL((aRGB0), 15, 3) | _SHIFTL((sbA0), 12, 3) | _SHIFTL((aA0), 9, 3))
#define GCCc1w1(sbRGB1,saA1,mA1,aRGB1,sbA1,aA1) (_SHIFTL((sbRGB1), 24, 4) | _SHIFTL((saA1), 21, 3) | _SHIFTL((mA1), 18, 3) | _SHIFTL((aRGB1), 6, 3) | _SHIFTL((sbA1), 3, 3) | _SHIFTL((aA1), 0, 3))
#define gDPSetCombineLERP(pkt,a0,b0,c0,d0,Aa0,Ab0,Ac0,Ad0,a1,b1,c1,d1,Aa1,Ab1,Ac1,Ad1) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_SETCOMBINE, 24, 8) | _SHIFTL(GCCc0w0(G_CCMUX_##a0, G_CCMUX_##c0, G_ACMUX_##Aa0, G_ACMUX_##Ac0) | GCCc1w0(G_CCMUX_##a1, G_CCMUX_##c1), 0, 24); _g->words.w1 = (unsigned int) (GCCc0w1(G_CCMUX_##b0, G_CCMUX_##d0, G_ACMUX_##Ab0, G_ACMUX_##Ad0) | GCCc1w1(G_CCMUX_##b1, G_ACMUX_##Aa1, G_ACMUX_##Ac1, G_CCMUX_##d1, G_ACMUX_##Ab1, G_ACMUX_##Ad1)); }
#define gsDPSetCombineLERP(a0,b0,c0,d0,Aa0,Ab0,Ac0,Ad0,a1,b1,c1,d1,Aa1,Ab1,Ac1,Ad1) { { _SHIFTL(G_SETCOMBINE, 24, 8) | _SHIFTL(GCCc0w0(G_CCMUX_##a0, G_CCMUX_##c0, G_ACMUX_##Aa0, G_ACMUX_##Ac0) | GCCc1w0(G_CCMUX_##a1, G_CCMUX_##c1), 0, 24), (unsigned int) (GCCc0w1(G_CCMUX_##b0, G_CCMUX_##d0, G_ACMUX_##Ab0, G_ACMUX_##Ad0) | GCCc1w1(G_CCMUX_##b1, G_ACMUX_##Aa1, G_ACMUX_##Ac1, G_CCMUX_##d1, G_ACMUX_##Ab1, G_ACMUX_##Ad1)) } }
#define gDPSetCombineMode(pkt,a,b) gDPSetCombineLERP(pkt, a, b)
#define gsDPSetCombineMode(a,b) gsDPSetCombineLERP(a, b)
#define gDPSetColor(pkt,c,d) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(c, 24, 8); _g->words.w1 = (unsigned int) (d); }
#define gsDPSetColor(c,d) { { _SHIFTL(c, 24, 8), (unsigned int) (d) } }
#define DPRGBColor(pkt,cmd,r,g,b,a) gDPSetColor(pkt, cmd, (_SHIFTL(r, 24, 8) | _SHIFTL(g, 16, 8) | _SHIFTL(b, 8, 8) | _SHIFTL(a, 0, 8)))
#define sDPRGBColor(cmd,r,g,b,a) gsDPSetColor(cmd, (_SHIFTL(r, 24, 8) | _SHIFTL(g, 16, 8) | _SHIFTL(b, 8, 8) | _SHIFTL(a, 0, 8)))
#define gDPSetEnvColor(pkt,r,g,b,a) DPRGBColor(pkt, G_SETENVCOLOR, r, g, b, a)
#define gsDPSetEnvColor(r,g,b,a) sDPRGBColor(G_SETENVCOLOR, r, g, b, a)
#define gDPSetBlendColor(pkt,r,g,b,a) DPRGBColor(pkt, G_SETBLENDCOLOR, r, g, b, a)
#define gsDPSetBlendColor(r,g,b,a) sDPRGBColor(G_SETBLENDCOLOR, r, g, b, a)
#define gDPSetFogColor(pkt,r,g,b,a) DPRGBColor(pkt, G_SETFOGCOLOR, r, g, b, a)
#define gsDPSetFogColor(r,g,b,a) sDPRGBColor(G_SETFOGCOLOR, r, g, b, a)
#define gDPSetFillColor(pkt,d) gDPSetColor(pkt, G_SETFILLCOLOR, (d))
#define gsDPSetFillColor(d) gsDPSetColor(G_SETFILLCOLOR, (d))
#define gDPSetPrimDepth(pkt,z,dz) gDPSetColor(pkt, G_SETPRIMDEPTH, _SHIFTL(z, 16, 16) | _SHIFTL(dz, 0, 16))
#define gsDPSetPrimDepth(z,dz) gsDPSetColor(G_SETPRIMDEPTH, _SHIFTL(z, 16, 16) | _SHIFTL(dz, 0, 16))
#define gDPSetPrimColor(pkt,m,l,r,g,b,a) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_SETPRIMCOLOR, 24, 8) | _SHIFTL(m, 8, 8) | _SHIFTL(l, 0, 8)); _g->words.w1 = (_SHIFTL(r, 24, 8) | _SHIFTL(g, 16, 8) | _SHIFTL(b, 8, 8) | _SHIFTL(a, 0, 8)); }
#define gsDPSetPrimColor(m,l,r,g,b,a) { { (_SHIFTL(G_SETPRIMCOLOR, 24, 8) | _SHIFTL(m, 8, 8) | _SHIFTL(l, 0, 8)), (_SHIFTL(r, 24, 8) | _SHIFTL(g, 16, 8) | _SHIFTL(b, 8, 8) | _SHIFTL(a, 0, 8)) } }
#define gDPSetOtherMode(pkt,mode0,mode1) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_RDPSETOTHERMODE, 24, 8) | _SHIFTL(mode0, 0, 24); _g->words.w1 = (unsigned int) (mode1); }
#define gsDPSetOtherMode(mode0,mode1) { { _SHIFTL(G_RDPSETOTHERMODE, 24, 8) | _SHIFTL(mode0, 0, 24), (unsigned int) (mode1) } }
#define G_TX_LOADTILE 7
#define G_TX_RENDERTILE 0
#define G_TX_NOMIRROR 0
#define G_TX_WRAP 0
#define G_TX_MIRROR 0x1
#define G_TX_CLAMP 0x2
#define G_TX_NOMASK 0
#define G_TX_NOLOD 0
#define MAX(a,b) ((a) > (b) ? (a) : (b))
#define MIN(a,b) ((a) < (b) ? (a) : (b))
#define G_TX_DXT_FRAC 11
#define G_TX_LDBLK_MAX_TXL 2047
#define TXL2WORDS(txls,b_txl) MAX(1, ((txls) * (b_txl) / 8))
#define CALC_DXT(width,b_txl) (((1 << G_TX_DXT_FRAC) + TXL2WORDS(width, b_txl) - 1) / TXL2WORDS(width, b_txl))
#define TXL2WORDS_4b(txls) MAX(1, ((txls) / 16))
#define CALC_DXT_4b(width) (((1 << G_TX_DXT_FRAC) + TXL2WORDS_4b(width) - 1) / TXL2WORDS_4b(width))
#define gDPLoadTileGeneric(pkt,c,tile,uls,ult,lrs,lrt) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(c, 24, 8) | _SHIFTL(uls, 12, 12) | _SHIFTL(ult, 0, 12); _g->words.w1 = _SHIFTL(tile, 24, 3) | _SHIFTL(lrs, 12, 12) | _SHIFTL(lrt, 0, 12); }
#define gsDPLoadTileGeneric(c,tile,uls,ult,lrs,lrt) { { _SHIFTL(c, 24, 8) | _SHIFTL(uls, 12, 12) | _SHIFTL(ult, 0, 12), _SHIFTL(tile, 24, 3) | _SHIFTL(lrs, 12, 12) | _SHIFTL(lrt, 0, 12) } }
#define gDPSetTileSize(pkt,t,uls,ult,lrs,lrt) gDPLoadTileGeneric(pkt, G_SETTILESIZE, t, uls, ult, lrs, lrt)
#define gsDPSetTileSize(t,uls,ult,lrs,lrt) gsDPLoadTileGeneric(G_SETTILESIZE, t, uls, ult, lrs, lrt)
#define gDPLoadTile(pkt,t,uls,ult,lrs,lrt) gDPLoadTileGeneric(pkt, G_LOADTILE, t, uls, ult, lrs, lrt)
#define gsDPLoadTile(t,uls,ult,lrs,lrt) gsDPLoadTileGeneric(G_LOADTILE, t, uls, ult, lrs, lrt)
#define gDPSetTile(pkt,fmt,siz,line,tmem,tile,palette,cmt,maskt,shiftt,cms,masks,shifts) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_SETTILE, 24, 8) | _SHIFTL(fmt, 21, 3) | _SHIFTL(siz, 19, 2) | _SHIFTL(line, 9, 9) | _SHIFTL(tmem, 0, 9); _g->words.w1 = _SHIFTL(tile, 24, 3) | _SHIFTL(palette, 20, 4) | _SHIFTL(cmt, 18, 2) | _SHIFTL(maskt, 14, 4) | _SHIFTL(shiftt, 10, 4) | _SHIFTL(cms, 8, 2) | _SHIFTL(masks, 4, 4) | _SHIFTL(shifts, 0, 4); }
#define gsDPSetTile(fmt,siz,line,tmem,tile,palette,cmt,maskt,shiftt,cms,masks,shifts) { { (_SHIFTL(G_SETTILE, 24, 8) | _SHIFTL(fmt, 21, 3) | _SHIFTL(siz, 19, 2) | _SHIFTL(line, 9, 9) | _SHIFTL(tmem, 0, 9)), (_SHIFTL(tile, 24, 3) | _SHIFTL(palette, 20, 4) | _SHIFTL(cmt, 18, 2) | _SHIFTL(maskt, 14, 4) | _SHIFTL(shiftt, 10, 4) | _SHIFTL(cms, 8, 2) | _SHIFTL(masks, 4, 4) | _SHIFTL(shifts, 0, 4)) } }
#define gDPLoadBlock(pkt,tile,uls,ult,lrs,dxt) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_LOADBLOCK, 24, 8) | _SHIFTL(uls, 12, 12) | _SHIFTL(ult, 0, 12)); _g->words.w1 = (_SHIFTL(tile, 24, 3) | _SHIFTL((MIN(lrs, G_TX_LDBLK_MAX_TXL)), 12, 12) | _SHIFTL(dxt, 0, 12)); }
#define gsDPLoadBlock(tile,uls,ult,lrs,dxt) { { (_SHIFTL(G_LOADBLOCK, 24, 8) | _SHIFTL(uls, 12, 12) | _SHIFTL(ult, 0, 12)), (_SHIFTL(tile, 24, 3) | _SHIFTL((MIN(lrs, G_TX_LDBLK_MAX_TXL)), 12, 12) | _SHIFTL(dxt, 0, 12)) } }
#define gDPLoadTLUTCmd(pkt,tile,count) { Gfx* _g = (Gfx*) pkt; _g->words.w0 = _SHIFTL(G_LOADTLUT, 24, 8); _g->words.w1 = _SHIFTL((tile), 24, 3) | _SHIFTL((count), 14, 10); }
#define gsDPLoadTLUTCmd(tile,count) { { _SHIFTL(G_LOADTLUT, 24, 8), _SHIFTL((tile), 24, 3) | _SHIFTL((count), 14, 10) } }
#define gDPLoadTextureBlock(pkt,timg,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz##_LOAD_BLOCK, 1, timg); gDPSetTile(pkt, fmt, siz##_LOAD_BLOCK, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, CALC_DXT(width, siz##_BYTES)); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((width) * siz##_LINE_BYTES) + 7) >> 3, 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadTextureBlockYuv(pkt,timg,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz##_LOAD_BLOCK, 1, timg); gDPSetTile(pkt, fmt, siz##_LOAD_BLOCK, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, CALC_DXT(width, siz##_BYTES)); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((width) * 1) + 7) >> 3, 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadTextureBlockS(pkt,timg,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz##_LOAD_BLOCK, 1, timg); gDPSetTile(pkt, fmt, siz##_LOAD_BLOCK, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, 0); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((width) * siz##_LINE_BYTES) + 7) >> 3, 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadMultiBlockS(pkt,timg,tmem,rtile,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz##_LOAD_BLOCK, 1, timg); gDPSetTile(pkt, fmt, siz##_LOAD_BLOCK, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, 0); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((width) * siz##_LINE_BYTES) + 7) >> 3, tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadTextureBlockYuvS(pkt,timg,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz##_LOAD_BLOCK, 1, timg); gDPSetTile(pkt, fmt, siz##_LOAD_BLOCK, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, 0); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((width) * 1) + 7) >> 3, 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define _gDPLoadTextureBlock(pkt,timg,tmem,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz##_LOAD_BLOCK, 1, timg); gDPSetTile(pkt, fmt, siz##_LOAD_BLOCK, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, CALC_DXT(width, siz##_BYTES)); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((width) * siz##_LINE_BYTES) + 7) >> 3, tmem, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define _gDPLoadTextureBlockTile(pkt,timg,tmem,rtile,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz##_LOAD_BLOCK, 1, timg); gDPSetTile(pkt, fmt, siz##_LOAD_BLOCK, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, CALC_DXT(width, siz##_BYTES)); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((width) * siz##_LINE_BYTES) + 7) >> 3, tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadMultiBlock(pkt,timg,tmem,rtile,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz##_LOAD_BLOCK, 1, timg); gDPSetTile(pkt, fmt, siz##_LOAD_BLOCK, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, CALC_DXT(width, siz##_BYTES)); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((width) * siz##_LINE_BYTES) + 7) >> 3, tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gsDPLoadTextureBlock(timg,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, siz##_LOAD_BLOCK, 1, timg), gsDPSetTile(fmt, siz##_LOAD_BLOCK, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, CALC_DXT(width, siz##_BYTES)), gsDPPipeSync(), gsDPSetTile(fmt, siz, ((((width) * siz##_LINE_BYTES) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define gsDPLoadTextureBlockS(timg,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, siz##_LOAD_BLOCK, 1, timg), gsDPSetTile(fmt, siz##_LOAD_BLOCK, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, 0), gsDPPipeSync(), gsDPSetTile(fmt, siz, ((((width) * siz##_LINE_BYTES) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define _gsDPLoadTextureBlock(timg,tmem,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, siz##_LOAD_BLOCK, 1, timg), gsDPSetTile(fmt, siz##_LOAD_BLOCK, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, CALC_DXT(width, siz##_BYTES)), gsDPPipeSync(), gsDPSetTile(fmt, siz, ((((width) * siz##_LINE_BYTES) + 7) >> 3), tmem, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define _gsDPLoadTextureBlockTile(timg,tmem,rtile,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, siz##_LOAD_BLOCK, 1, timg), gsDPSetTile(fmt, siz##_LOAD_BLOCK, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, CALC_DXT(width, siz##_BYTES)), gsDPPipeSync(), gsDPSetTile(fmt, siz, ((((width) * siz##_LINE_BYTES) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define gsDPLoadMultiBlock(timg,tmem,rtile,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, siz##_LOAD_BLOCK, 1, timg), gsDPSetTile(fmt, siz##_LOAD_BLOCK, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, CALC_DXT(width, siz##_BYTES)), gsDPPipeSync(), gsDPSetTile(fmt, siz, ((((width) * siz##_LINE_BYTES) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define gsDPLoadMultiBlockS(timg,tmem,rtile,fmt,siz,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, siz##_LOAD_BLOCK, 1, timg), gsDPSetTile(fmt, siz##_LOAD_BLOCK, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + siz##_INCR) >> siz##_SHIFT) - 1, 0), gsDPPipeSync(), gsDPSetTile(fmt, siz, ((((width) * siz##_LINE_BYTES) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define gDPLoadTextureBlock_4b(pkt,timg,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, G_IM_SIZ_16b, 1, timg); gDPSetTile(pkt, fmt, G_IM_SIZ_16b, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, CALC_DXT_4b(width)); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadTextureBlock_4bS(pkt,timg,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, G_IM_SIZ_16b, 1, timg); gDPSetTile(pkt, fmt, G_IM_SIZ_16b, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, 0); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadMultiBlock_4b(pkt,timg,tmem,rtile,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, G_IM_SIZ_16b, 1, timg); gDPSetTile(pkt, fmt, G_IM_SIZ_16b, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, CALC_DXT_4b(width)); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadMultiBlock_4bS(pkt,timg,tmem,rtile,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, G_IM_SIZ_16b, 1, timg); gDPSetTile(pkt, fmt, G_IM_SIZ_16b, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, 0); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define _gDPLoadTextureBlock_4b(pkt,timg,tmem,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, G_IM_SIZ_16b, 1, timg); gDPSetTile(pkt, fmt, G_IM_SIZ_16b, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadBlock(pkt, G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, CALC_DXT_4b(width)); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), tmem, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC) }
#define gsDPLoadTextureBlock_4b(timg,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, G_IM_SIZ_16b, 1, timg), gsDPSetTile(fmt, G_IM_SIZ_16b, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, CALC_DXT_4b(width)), gsDPPipeSync(), gsDPSetTile(fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define gsDPLoadTextureBlock_4bS(timg,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, G_IM_SIZ_16b, 1, timg), gsDPSetTile(fmt, G_IM_SIZ_16b, 0, 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, 0), gsDPPipeSync(), gsDPSetTile(fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define gsDPLoadMultiBlock_4b(timg,tmem,rtile,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, G_IM_SIZ_16b, 1, timg), gsDPSetTile(fmt, G_IM_SIZ_16b, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, CALC_DXT_4b(width)), gsDPPipeSync(), gsDPSetTile(fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define gsDPLoadMultiBlock_4bS(timg,tmem,rtile,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, G_IM_SIZ_16b, 1, timg), gsDPSetTile(fmt, G_IM_SIZ_16b, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, 0), gsDPPipeSync(), gsDPSetTile(fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(rtile, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define _gsDPLoadTextureBlock_4b(timg,tmem,fmt,width,height,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, G_IM_SIZ_16b, 1, timg), gsDPSetTile(fmt, G_IM_SIZ_16b, 0, tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadBlock(G_TX_LOADTILE, 0, 0, (((width) * (height) + 3) >> 2) - 1, CALC_DXT_4b(width)), gsDPPipeSync(), gsDPSetTile(fmt, G_IM_SIZ_4b, ((((width) >> 1) + 7) >> 3), tmem, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(G_TX_RENDERTILE, 0, 0, ((width) -1) << G_TEXTURE_IMAGE_FRAC, ((height) -1) << G_TEXTURE_IMAGE_FRAC)
#define gDPLoadTextureTile(pkt,timg,fmt,siz,width,height,uls,ult,lrs,lrt,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz, width, timg); gDPSetTile(pkt, fmt, siz, (((((lrs) - (uls) + 1) * siz##_TILE_BYTES) + 7) >> 3), 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadTile(pkt, G_TX_LOADTILE, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((((lrs) - (uls) + 1) * siz##_LINE_BYTES) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadMultiTile(pkt,timg,tmem,rtile,fmt,siz,width,height,uls,ult,lrs,lrt,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, siz, width, timg); gDPSetTile(pkt, fmt, siz, (((((lrs) - (uls) + 1) * siz##_TILE_BYTES) + 7) >> 3), tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadTile(pkt, G_TX_LOADTILE, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, siz, (((((lrs) - (uls) + 1) * siz##_LINE_BYTES) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, rtile, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC) }
#define gsDPLoadTextureTile(timg,fmt,siz,width,height,uls,ult,lrs,lrt,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, siz, width, timg), gsDPSetTile(fmt, siz, (((((lrs) - (uls) + 1) * siz##_TILE_BYTES) + 7) >> 3), 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadTile(G_TX_LOADTILE, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC), gsDPPipeSync(), gsDPSetTile( fmt, siz, (((((lrs) - (uls) + 1) * siz##_LINE_BYTES) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(G_TX_RENDERTILE, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC)
#define gsDPLoadMultiTile(timg,tmem,rtile,fmt,siz,width,height,uls,ult,lrs,lrt,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, siz, width, timg), gsDPSetTile( fmt, siz, (((((lrs) - (uls) + 1) * siz##_TILE_BYTES) + 7) >> 3), tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadTile(G_TX_LOADTILE, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC), gsDPPipeSync(), gsDPSetTile(fmt, siz, (((((lrs) - (uls) + 1) * siz##_LINE_BYTES) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(rtile, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC)
#define gDPLoadTextureTile_4b(pkt,timg,fmt,width,height,uls,ult,lrs,lrt,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, G_IM_SIZ_8b, ((width) >> 1), timg); gDPSetTile(pkt, fmt, G_IM_SIZ_8b, (((((lrs) - (uls) + 1) >> 1) + 7) >> 3), 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadTile(pkt, G_TX_LOADTILE, (uls) << (G_TEXTURE_IMAGE_FRAC - 1), (ult) << (G_TEXTURE_IMAGE_FRAC), (lrs) << (G_TEXTURE_IMAGE_FRAC - 1), (lrt) << (G_TEXTURE_IMAGE_FRAC)); gDPPipeSync(pkt); gDPSetTile( pkt, fmt, G_IM_SIZ_4b, (((((lrs) - (uls) + 1) >> 1) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, G_TX_RENDERTILE, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC) }
#define gDPLoadMultiTile_4b(pkt,timg,tmem,rtile,fmt,width,height,uls,ult,lrs,lrt,pal,cms,cmt,masks,maskt,shifts,shiftt) { gDPSetTextureImage(pkt, fmt, G_IM_SIZ_8b, ((width) >> 1), timg); gDPSetTile(pkt, fmt, G_IM_SIZ_8b, (((((lrs) - (uls) + 1) >> 1) + 7) >> 3), tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts); gDPLoadSync(pkt); gDPLoadTile(pkt, G_TX_LOADTILE, (uls) << (G_TEXTURE_IMAGE_FRAC - 1), (ult) << (G_TEXTURE_IMAGE_FRAC), (lrs) << (G_TEXTURE_IMAGE_FRAC - 1), (lrt) << (G_TEXTURE_IMAGE_FRAC)); gDPPipeSync(pkt); gDPSetTile(pkt, fmt, G_IM_SIZ_4b, (((((lrs) - (uls) + 1) >> 1) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts); gDPSetTileSize(pkt, rtile, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC) }
#define gsDPLoadTextureTile_4b(timg,fmt,width,height,uls,ult,lrs,lrt,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, G_IM_SIZ_8b, ((width) >> 1), timg), gsDPSetTile(fmt, G_IM_SIZ_8b, (((((lrs) - (uls) + 1) >> 1) + 7) >> 3), 0, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadTile(G_TX_LOADTILE, (uls) << (G_TEXTURE_IMAGE_FRAC - 1), (ult) << (G_TEXTURE_IMAGE_FRAC), (lrs) << (G_TEXTURE_IMAGE_FRAC - 1), (lrt) << (G_TEXTURE_IMAGE_FRAC)), gsDPPipeSync(), gsDPSetTile(fmt, G_IM_SIZ_4b, (((((lrs) - (uls) + 1) >> 1) + 7) >> 3), 0, G_TX_RENDERTILE, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(G_TX_RENDERTILE, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC)
#define gsDPLoadMultiTile_4b(timg,tmem,rtile,fmt,width,height,uls,ult,lrs,lrt,pal,cms,cmt,masks,maskt,shifts,shiftt) gsDPSetTextureImage(fmt, G_IM_SIZ_8b, ((width) >> 1), timg), gsDPSetTile(fmt, G_IM_SIZ_8b, (((((lrs) - (uls) + 1) >> 1) + 7) >> 3), tmem, G_TX_LOADTILE, 0, cmt, maskt, shiftt, cms, masks, shifts), gsDPLoadSync(), gsDPLoadTile(G_TX_LOADTILE, (uls) << (G_TEXTURE_IMAGE_FRAC - 1), (ult) << (G_TEXTURE_IMAGE_FRAC), (lrs) << (G_TEXTURE_IMAGE_FRAC - 1), (lrt) << (G_TEXTURE_IMAGE_FRAC)), gsDPPipeSync(), gsDPSetTile(fmt, G_IM_SIZ_4b, (((((lrs) - (uls) + 1) >> 1) + 7) >> 3), tmem, rtile, pal, cmt, maskt, shiftt, cms, masks, shifts), gsDPSetTileSize(rtile, (uls) << G_TEXTURE_IMAGE_FRAC, (ult) << G_TEXTURE_IMAGE_FRAC, (lrs) << G_TEXTURE_IMAGE_FRAC, (lrt) << G_TEXTURE_IMAGE_FRAC)
#define gDPLoadTLUT_pal16(pkt,pal,dram) { gDPSetTextureImage(pkt, G_IM_FMT_RGBA, G_IM_SIZ_16b, 1, dram); gDPTileSync(pkt); gDPSetTile(pkt, 0, 0, 0, (256 + (((pal) & 0xf) * 16)), G_TX_LOADTILE, 0, 0, 0, 0, 0, 0, 0); gDPLoadSync(pkt); gDPLoadTLUTCmd(pkt, G_TX_LOADTILE, 15); gDPPipeSync(pkt) }
#define gsDPLoadTLUT_pal16(pal,dram) gsDPSetTextureImage(G_IM_FMT_RGBA, G_IM_SIZ_16b, 1, dram), gsDPTileSync(), gsDPSetTile(0, 0, 0, (256 + (((pal) & 0xf) * 16)), G_TX_LOADTILE, 0, 0, 0, 0, 0, 0, 0), gsDPLoadSync(), gsDPLoadTLUTCmd(G_TX_LOADTILE, 15), gsDPPipeSync()
#define gDPLoadTLUT_pal256(pkt,dram) { gDPSetTextureImage(pkt, G_IM_FMT_RGBA, G_IM_SIZ_16b, 1, dram); gDPTileSync(pkt); gDPSetTile(pkt, 0, 0, 0, 256, G_TX_LOADTILE, 0, 0, 0, 0, 0, 0, 0); gDPLoadSync(pkt); gDPLoadTLUTCmd(pkt, G_TX_LOADTILE, 255); gDPPipeSync(pkt) }
#define gsDPLoadTLUT_pal256(dram) gsDPSetTextureImage(G_IM_FMT_RGBA, G_IM_SIZ_16b, 1, dram), gsDPTileSync(), gsDPSetTile(0, 0, 0, 256, G_TX_LOADTILE, 0, 0, 0, 0, 0, 0, 0), gsDPLoadSync(), gsDPLoadTLUTCmd(G_TX_LOADTILE, 255), gsDPPipeSync()
#define gDPLoadTLUT(pkt,count,tmemaddr,dram) { gDPSetTextureImage(pkt, G_IM_FMT_RGBA, G_IM_SIZ_16b, 1, dram); gDPTileSync(pkt); gDPSetTile(pkt, 0, 0, 0, tmemaddr, G_TX_LOADTILE, 0, 0, 0, 0, 0, 0, 0); gDPLoadSync(pkt); gDPLoadTLUTCmd(pkt, G_TX_LOADTILE, ((count) -1)); gDPPipeSync(pkt); }
#define gsDPLoadTLUT(count,tmemaddr,dram) gsDPSetTextureImage(G_IM_FMT_RGBA, G_IM_SIZ_16b, 1, dram), gsDPTileSync(), gsDPSetTile(0, 0, 0, tmemaddr, G_TX_LOADTILE, 0, 0, 0, 0, 0, 0, 0), gsDPLoadSync(), gsDPLoadTLUTCmd(G_TX_LOADTILE, ((count) -1)), gsDPPipeSync()
#define gDPSetScissor(pkt,mode,ulx,uly,lrx,lry) { Gfx* _g = (Gfx*) pkt; _g->words.w0 = _SHIFTL(G_SETSCISSOR, 24, 8) | _SHIFTL((int) ((float) (ulx) * 4.0F), 12, 12) | _SHIFTL((int) ((float) (uly) * 4.0F), 0, 12); _g->words.w1 = _SHIFTL(mode, 24, 2) | _SHIFTL((int) ((float) (lrx) * 4.0F), 12, 12) | _SHIFTL((int) ((float) (lry) * 4.0F), 0, 12); }
#define gDPSetScissorFrac(pkt,mode,ulx,uly,lrx,lry) { Gfx* _g = (Gfx*) pkt; _g->words.w0 = _SHIFTL(G_SETSCISSOR, 24, 8) | _SHIFTL((int) ((ulx)), 12, 12) | _SHIFTL((int) ((uly)), 0, 12); _g->words.w1 = _SHIFTL(mode, 24, 2) | _SHIFTL((int) ((lrx)), 12, 12) | _SHIFTL((int) ((lry)), 0, 12); }
#define gsDPSetScissor(mode,ulx,uly,lrx,lry) { { _SHIFTL(G_SETSCISSOR, 24, 8) | _SHIFTL((int) ((float) (ulx) * 4.0F), 12, 12) | _SHIFTL((int) ((float) (uly) * 4.0F), 0, 12), _SHIFTL(mode, 24, 2) | _SHIFTL((int) ((float) (lrx) * 4.0F), 12, 12) | _SHIFTL((int) ((float) (lry) * 4.0F), 0, 12) } }
#define gsDPSetScissorFrac(mode,ulx,uly,lrx,lry) { { _SHIFTL(G_SETSCISSOR, 24, 8) | _SHIFTL((int) ((ulx)), 12, 12) | _SHIFTL((int) ((uly)), 0, 12), _SHIFTL(mode, 24, 2) | _SHIFTL((int) (lrx), 12, 12) | _SHIFTL((int) (lry), 0, 12) } }
#define gDPFillRectangle(pkt,ulx,uly,lrx,lry) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_FILLRECT, 24, 8) | _SHIFTL((lrx), 14, 10) | _SHIFTL((lry), 2, 10)); _g->words.w1 = (_SHIFTL((ulx), 14, 10) | _SHIFTL((uly), 2, 10)); }
#define gsDPFillRectangle(ulx,uly,lrx,lry) { { (_SHIFTL(G_FILLRECT, 24, 8) | _SHIFTL((lrx), 14, 10) | _SHIFTL((lry), 2, 10)), (_SHIFTL((ulx), 14, 10) | _SHIFTL((uly), 2, 10)) } }
#define gDPScisFillRectangle(pkt,ulx,uly,lrx,lry) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_FILLRECT, 24, 8) | _SHIFTL(MAX((lrx), 0), 14, 10) | _SHIFTL(MAX((lry), 0), 2, 10)); _g->words.w1 = (_SHIFTL(MAX((ulx), 0), 14, 10) | _SHIFTL(MAX((uly), 0), 2, 10)); }
#define gDPSetConvert(pkt,k0,k1,k2,k3,k4,k5) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_SETCONVERT, 24, 8) | _SHIFTL(k0, 13, 9) | _SHIFTL(k1, 4, 9) | _SHIFTR(k2, 5, 4)); _g->words.w1 = (_SHIFTL(k2, 27, 5) | _SHIFTL(k3, 18, 9) | _SHIFTL(k4, 9, 9) | _SHIFTL(k5, 0, 9)); }
#define gsDPSetConvert(k0,k1,k2,k3,k4,k5) { { (_SHIFTL(G_SETCONVERT, 24, 8) | _SHIFTL(k0, 13, 9) | _SHIFTL(k1, 4, 9) | _SHIFTR(k2, 5, 4)), (_SHIFTL(k2, 27, 5) | _SHIFTL(k3, 18, 9) | _SHIFTL(k4, 9, 9) | _SHIFTL(k5, 0, 9)) } }
#define gDPSetKeyR(pkt,cR,sR,wR) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(G_SETKEYR, 24, 8); _g->words.w1 = (_SHIFTL(wR, 16, 12) | _SHIFTL(cR, 8, 8) | _SHIFTL(sR, 0, 8)); }
#define gsDPSetKeyR(cR,sR,wR) { { _SHIFTL(G_SETKEYR, 24, 8), _SHIFTL(wR, 16, 12) | _SHIFTL(cR, 8, 8) | _SHIFTL(sR, 0, 8) } }
#define gDPSetKeyGB(pkt,cG,sG,wG,cB,sB,wB) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_SETKEYGB, 24, 8) | _SHIFTL(wG, 12, 12) | _SHIFTL(wB, 0, 12)); _g->words.w1 = (_SHIFTL(cG, 24, 8) | _SHIFTL(sG, 16, 8) | _SHIFTL(cB, 8, 8) | _SHIFTL(sB, 0, 8)); }
#define gsDPSetKeyGB(cG,sG,wG,cB,sB,wB) { { (_SHIFTL(G_SETKEYGB, 24, 8) | _SHIFTL(wG, 12, 12) | _SHIFTL(wB, 0, 12)), (_SHIFTL(cG, 24, 8) | _SHIFTL(sG, 16, 8) | _SHIFTL(cB, 8, 8) | _SHIFTL(sB, 0, 8)) } }
#define gDPNoParam(pkt,cmd) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(cmd, 24, 8); _g->words.w1 = 0; }
#define gsDPNoParam(cmd) { { _SHIFTL(cmd, 24, 8), 0 } }
#define gDPParam(pkt,cmd,param) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = _SHIFTL(cmd, 24, 8); _g->words.w1 = (param); }
#define gsDPParam(cmd,param) { { _SHIFTL(cmd, 24, 8), (param) } }
#define gsDPTextureRectangle(xl,yl,xh,yh,tile,s,t,dsdx,dtdy) {{ (_SHIFTL(G_TEXRECT, 24, 8) | _SHIFTL(xh, 12, 12) | _SHIFTL(yh, 0, 12)), (_SHIFTL(tile, 24, 3) | _SHIFTL(xl, 12, 12) | _SHIFTL(yl, 0, 12)), }}, { { _SHIFTL(s, 16, 16) | _SHIFTL(t, 0, 16), _SHIFTL(dsdx, 16, 16) | _SHIFTL(dtdy, 0, 16) } }
#define gDPTextureRectangle(pkt,xl,yl,xh,yh,tile,s,t,dsdx,dtdy) { Gfx* _g = (Gfx*) (pkt); if (pkt) ; _g->words.w0 = (_SHIFTL(G_TEXRECT, 24, 8) | _SHIFTL(xh, 12, 12) | _SHIFTL(yh, 0, 12)); _g->words.w1 = (_SHIFTL(tile, 24, 3) | _SHIFTL(xl, 12, 12) | _SHIFTL(yl, 0, 12)); _g++; _g->words.w0 = (_SHIFTL(s, 16, 16) | _SHIFTL(t, 0, 16)); _g->words.w1 = (_SHIFTL(dsdx, 16, 16) | _SHIFTL(dtdy, 0, 16)); }
#define gsDPTextureRectangleFlip(xl,yl,xh,yh,tile,s,t,dsdx,dtdy) {{ (_SHIFTL(G_TEXRECTFLIP, 24, 8) | _SHIFTL(xh, 12, 12) | _SHIFTL(yh, 0, 12)), (_SHIFTL(tile, 24, 3) | _SHIFTL(xl, 12, 12) | _SHIFTL(yl, 0, 12)), }}, { { _SHIFTL(s, 16, 16) | _SHIFTL(t, 0, 16), _SHIFTL(dsdx, 16, 16) | _SHIFTL(dtdy, 0, 16) } }
#define gDPTextureRectangleFlip(pkt,xl,yl,xh,yh,tile,s,t,dsdx,dtdy) { Gfx* _g = (Gfx*) (pkt); if (pkt) ; _g->words.w0 = (_SHIFTL(G_TEXRECTFLIP, 24, 8) | _SHIFTL(xh, 12, 12) | _SHIFTL(yh, 0, 12)); _g->words.w1 = (_SHIFTL(tile, 24, 3) | _SHIFTL(xl, 12, 12) | _SHIFTL(yl, 0, 12)); _g++; _g->words.w0 = (_SHIFTL(s, 16, 16) | _SHIFTL(t, 0, 16)); _g->words.w1 = (_SHIFTL(dsdx, 16, 16) | _SHIFTL(dtdy, 0, 16)); }
#define gsSPTextureRectangle(xl,yl,xh,yh,tile,s,t,dsdx,dtdy) {{(_SHIFTL(G_TEXRECT, 24, 8) | _SHIFTL(xh, 12, 12) | _SHIFTL(yh, 0, 12)), (_SHIFTL(tile, 24, 3) | _SHIFTL(xl, 12, 12) | _SHIFTL(yl, 0, 12))}}, gsImmp1(G_RDPHALF_1, (_SHIFTL(s, 16, 16) | _SHIFTL(t, 0, 16))), gsImmp1(G_RDPHALF_2, (_SHIFTL(dsdx, 16, 16) | _SHIFTL(dtdy, 0, 16)))
#define gSPTextureRectangle(pkt,xl,yl,xh,yh,tile,s,t,dsdx,dtdy) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_TEXRECT, 24, 8) | _SHIFTL(xh, 12, 12) | _SHIFTL(yh, 0, 12)); _g->words.w1 = (_SHIFTL(tile, 24, 3) | _SHIFTL(xl, 12, 12) | _SHIFTL(yl, 0, 12)); gImmp1(pkt, G_RDPHALF_1, (_SHIFTL(s, 16, 16) | _SHIFTL(t, 0, 16))); gImmp1(pkt, G_RDPHALF_2, (_SHIFTL(dsdx, 16, 16) | _SHIFTL(dtdy, 0, 16))); }
#define gSPScisTextureRectangle(pkt,xl,yl,xh,yh,tile,s,t,dsdx,dtdy) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_TEXRECT, 24, 8) | _SHIFTL(MAX((s16) (xh), 0), 12, 12) | _SHIFTL(MAX((s16) (yh), 0), 0, 12)); _g->words.w1 = (_SHIFTL((tile), 24, 3) | _SHIFTL(MAX((s16) (xl), 0), 12, 12) | _SHIFTL(MAX((s16) (yl), 0), 0, 12)); gImmp1( pkt, G_RDPHALF_1, (_SHIFTL( ((s) - (((s16) (xl) < 0) ? (((s16) (dsdx) < 0) ? (MAX((((s16) (xl) * (s16) (dsdx)) >> 7), 0)) : (MIN((((s16) (xl) * (s16) (dsdx)) >> 7), 0))) : 0)), 16, 16) | _SHIFTL( ((t) - (((yl) < 0) ? (((s16) (dtdy) < 0) ? (MAX((((s16) (yl) * (s16) (dtdy)) >> 7), 0)) : (MIN((((s16) (yl) * (s16) (dtdy)) >> 7), 0))) : 0)), 0, 16))); gImmp1(pkt, G_RDPHALF_2, (_SHIFTL((dsdx), 16, 16) | _SHIFTL((dtdy), 0, 16))); }
#define gsSPTextureRectangleFlip(xl,yl,xh,yh,tile,s,t,dsdx,dtdy) {{(_SHIFTL(G_TEXRECTFLIP, 24, 8) | _SHIFTL(xh, 12, 12) | _SHIFTL(yh, 0, 12)), (_SHIFTL(tile, 24, 3) | _SHIFTL(xl, 12, 12) | _SHIFTL(yl, 0, 12))}}, gsImmp1(G_RDPHALF_1, (_SHIFTL(s, 16, 16) | _SHIFTL(t, 0, 16))), gsImmp1(G_RDPHALF_2, (_SHIFTL(dsdx, 16, 16) | _SHIFTL(dtdy, 0, 16)))
#define gSPTextureRectangleFlip(pkt,xl,yl,xh,yh,tile,s,t,dsdx,dtdy) { Gfx* _g = (Gfx*) (pkt); _g->words.w0 = (_SHIFTL(G_TEXRECTFLIP, 24, 8) | _SHIFTL(xh, 12, 12) | _SHIFTL(yh, 0, 12)); _g->words.w1 = (_SHIFTL(tile, 24, 3) | _SHIFTL(xl, 12, 12) | _SHIFTL(yl, 0, 12)); gImmp1(pkt, G_RDPHALF_1, (_SHIFTL(s, 16, 16) | _SHIFTL(t, 0, 16))); gImmp1(pkt, G_RDPHALF_2, (_SHIFTL(dsdx, 16, 16) | _SHIFTL(dtdy, 0, 16))); }
#define gsDPWord(wordhi,wordlo) gsImmp1(G_RDPHALF_1, (unsigned int) (wordhi)), gsImmp1(G_RDPHALF_2, (unsigned int) (wordlo))
#define gDPWord(pkt,wordhi,wordlo) { Gfx* _g = (Gfx*) (pkt); gImmp1(pkt, G_RDPHALF_1, (unsigned int) (wordhi)); gImmp1(pkt, G_RDPHALF_2, (unsigned int) (wordlo)); }
#define gDPFullSync(pkt) gDPNoParam(pkt, G_RDPFULLSYNC)
#define gsDPFullSync() gsDPNoParam(G_RDPFULLSYNC)
#define gDPTileSync(pkt) gDPNoParam(pkt, G_RDPTILESYNC)
#define gsDPTileSync() gsDPNoParam(G_RDPTILESYNC)
#define gDPPipeSync(pkt) gDPNoParam(pkt, G_RDPPIPESYNC)
#define gsDPPipeSync() gsDPNoParam(G_RDPPIPESYNC)
#define gDPLoadSync(pkt) gDPNoParam(pkt, G_RDPLOADSYNC)
#define gsDPLoadSync() gsDPNoParam(G_RDPLOADSYNC)
#define gDPNoOp(pkt) gDPNoParam(pkt, G_NOOP)
#define gsDPNoOp() gsDPNoParam(G_NOOP)
#define gDPNoOpTag(pkt,tag) gDPParam(pkt, G_NOOP, tag)
#define gsDPNoOpTag(tag) gsDPParam(G_NOOP, tag)
#define _ABI_H_ 
#define A_SPNOOP 0
#define A_ADPCM 1
#define A_CLEARBUFF 2
#define A_ENVMIXER 3
#define A_LOADBUFF 4
#define A_RESAMPLE 5
#define A_SAVEBUFF 6
#define A_SEGMENT 7
#define A_SETBUFF 8
#define A_SETVOL 9
#define A_DMEMMOVE 10
#define A_LOADADPCM 11
#define A_MIXER 12
#define A_INTERLEAVE 13
#define A_POLEF 14
#define A_SETLOOP 15
#define ACMD_SIZE 32
#define A_INIT 0x01
#define A_CONTINUE 0x00
#define A_LOOP 0x02
#define A_OUT 0x02
#define A_LEFT 0x02
#define A_RIGHT 0x00
#define A_VOL 0x04
#define A_RATE 0x00
#define A_AUX 0x08
#define A_NOAUX 0x00
#define A_MAIN 0x00
#define A_MIX 0x10
#define ADPCMVSIZE 8
#define ADPCMFSIZE 16
#define UNITY_PITCH 0x8000
#define MAX_RATIO 1.99996
#define aADPCMdec(pkt,f,s) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_ADPCM, 24, 8) | _SHIFTL(f, 16, 8); _a->words.w1 = (unsigned int) (s); }
#define aPoleFilter(pkt,f,g,s) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = (_SHIFTL(A_POLEF, 24, 8) | _SHIFTL(f, 16, 8) | _SHIFTL(g, 0, 16)); _a->words.w1 = (unsigned int) (s); }
#define aClearBuffer(pkt,d,c) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_CLEARBUFF, 24, 8) | _SHIFTL(d, 0, 24); _a->words.w1 = (unsigned int) (c); }
#define aEnvMixer(pkt,f,s) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_ENVMIXER, 24, 8) | _SHIFTL(f, 16, 8); _a->words.w1 = (unsigned int) (s); }
#define aInterleave(pkt,l,r) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_INTERLEAVE, 24, 8); _a->words.w1 = _SHIFTL(l, 16, 16) | _SHIFTL(r, 0, 16); }
#define aLoadBuffer(pkt,s) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_LOADBUFF, 24, 8); _a->words.w1 = (unsigned int) (s); }
#define aMix(pkt,f,g,i,o) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = (_SHIFTL(A_MIXER, 24, 8) | _SHIFTL(f, 16, 8) | _SHIFTL(g, 0, 16)); _a->words.w1 = _SHIFTL(i, 16, 16) | _SHIFTL(o, 0, 16); }
#define aPan(pkt,f,d,s) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = (_SHIFTL(A_PAN, 24, 8) | _SHIFTL(f, 16, 8) | _SHIFTL(d, 0, 16)); _a->words.w1 = (unsigned int) (s); }
#define aResample(pkt,f,p,s) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = (_SHIFTL(A_RESAMPLE, 24, 8) | _SHIFTL(f, 16, 8) | _SHIFTL(p, 0, 16)); _a->words.w1 = (unsigned int) (s); }
#define aSaveBuffer(pkt,s) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_SAVEBUFF, 24, 8); _a->words.w1 = (unsigned int) (s); }
#define aSegment(pkt,s,b) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_SEGMENT, 24, 8); _a->words.w1 = _SHIFTL(s, 24, 8) | _SHIFTL(b, 0, 24); }
#define aSetBuffer(pkt,f,i,o,c) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = (_SHIFTL(A_SETBUFF, 24, 8) | _SHIFTL(f, 16, 8) | _SHIFTL(i, 0, 16)); _a->words.w1 = _SHIFTL(o, 16, 16) | _SHIFTL(c, 0, 16); }
#define aSetVolume(pkt,f,v,t,r) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = (_SHIFTL(A_SETVOL, 24, 8) | _SHIFTL(f, 16, 16) | _SHIFTL(v, 0, 16)); _a->words.w1 = _SHIFTL(t, 16, 16) | _SHIFTL(r, 0, 16); }
#define aSetLoop(pkt,a) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_SETLOOP, 24, 8); _a->words.w1 = (unsigned int) (a); }
#define aDMEMMove(pkt,i,o,c) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_DMEMMOVE, 24, 8) | _SHIFTL(i, 0, 24); _a->words.w1 = _SHIFTL(o, 16, 16) | _SHIFTL(c, 0, 16); }
#define aLoadADPCM(pkt,c,d) { Acmd* _a = (Acmd*) pkt; _a->words.w0 = _SHIFTL(A_LOADADPCM, 24, 8) | _SHIFTL(c, 0, 24); _a->words.w1 = (unsigned int) d; }
#define M_GFXTASK 1
#define M_AUDTASK 2
#define M_VIDTASK 3
#define M_HVQTASK 6
#define M_HVQMTASK 7
#define NUM_SEGMENTS (16)
#define SEGMENT_OFFSET(a) ((unsigned int) (a) & 0x00ffffff)
#define SEGMENT_NUMBER(a) (((unsigned int) (a) << 4) >> 28)
#define SEGMENT_ADDR(num,off) (((num) << 24) + (off))
#define _OS_VERSION_H_ 
#define VERSION_D 1
#define VERSION_E 2
#define VERSION_F 3
#define VERSION_G 4
#define VERSION_H 5
#define VERSION_I 6
#define VERSION_J 7
#define VERSION_K 8
#define VERSION_L 9
#define OS_MAJOR_VERSION BUILD_VERSION_STRING
#define OS_MINOR_VERSION 0
#define _SPTASK_H_ 
#define OS_TASK_YIELDED 0x0001
#define OS_TASK_DP_WAIT 0x0002
#define OS_TASK_LOADABLE 0x0004
#define OS_TASK_SP_ONLY 0x0008
#define OS_TASK_USR0 0x0010
#define OS_TASK_USR1 0x0020
#define OS_TASK_USR2 0x0040
#define OS_TASK_USR3 0x0080
#define OS_YIELD_DATA_SIZE 0xc00
#define OS_YIELD_AUDIO_SIZE 0x400
#define osSpTaskStart(tp) { osSpTaskLoad((tp)); osSpTaskStartGo((tp)); }
#define M_PI 3.14159265358979323846
#define M_DTOR (3.14159265358979323846 / 180.0)
#define FTOFIX32(x) (long) ((x) * (float) 0x00010000)
#define FIX32TOF(x) ((float) (x) * (1.0f / (float) 0x00010000))
#define FTOFRAC8(x) ((int) MIN(((x) * (128.0f)), 127.0f) & 0xff)
#define FILTER_WRAP 0
#define FILTER_CLAMP 1
#define RAND(x) (guRandom() % x)
#define GU_PARSERDP_VERBOSE 1
#define GU_PARSERDP_PRAREA 2
#define GU_PARSERDP_PRHISTO 4
#define GU_PARSERDP_DUMPONLY 32
#define GU_BLINKRDP_HILITE 1
#define GU_BLINKRDP_EXTRACT 2
#define GU_PARSEGBI_ROWMAJOR 1
#define GU_PARSEGBI_NONEST 2
#define GU_PARSEGBI_FLTMTX 4
#define GU_PARSEGBI_SHOWDMA 8
#define GU_PARSEGBI_ALLMTX 16
#define GU_PARSEGBI_DUMPONLY 32
#define GU_PARSE_GBI_TYPE 1
#define GU_PARSE_RDP_TYPE 2
#define GU_PARSE_READY 3
#define GU_PARSE_MEM_BLOCK 4
#define GU_PARSE_ABI_TYPE 5
#define GU_PARSE_STRING_TYPE 6
#define __LIB_AUDIO__ 
#define AL_FX_BUFFER_SIZE 8192
#define AL_FRAME_INIT -1
#define AL_USEC_PER_FRAME 16000
#define AL_MAX_PRIORITY 127
#define AL_GAIN_CHANGE_TIME 1000
#define AL_PAN_CENTER 64
#define AL_PAN_LEFT 0
#define AL_PAN_RIGHT 127
#define AL_VOL_FULL 127
#define AL_KEY_MIN 0
#define AL_KEY_MAX 127
#define AL_DEFAULT_FXMIX 0
#define AL_SUSTAIN 63
#define ALFailIf(condition,error) if (condition) { return; }
#define ALFlagFailIf(condition,flag,error) if (condition) { return; }
#define AL_HEAP_DEBUG 1
#define AL_HEAP_MAGIC 0x20736a73
#define AL_HEAP_INIT 0
#define alHeapAlloc(hp,elem,size) alHeapDBAlloc(0, 0, (hp), (elem), (size))
#define AL_FX_NONE 0
#define AL_FX_SMALLROOM 1
#define AL_FX_BIGROOM 2
#define AL_FX_CHORUS 3
#define AL_FX_FLANGE 4
#define AL_FX_ECHO 5
#define AL_FX_CUSTOM 6
#define AL_BANK_VERSION 0x4231
#define AL_SEQBANK_VERSION 'S1'
#define AL_STOPPED 0
#define AL_PLAYING 1
#define AL_STOPPING 2
#define AL_DEFAULT_PRIORITY 5
#define AL_DEFAULT_VOICE 0
#define AL_MAX_CHANNELS 16
#define AL_EVTQ_END 0x7fffffff
#define AL_CMIDI_BLOCK_CODE 0xFE
#define AL_CMIDI_LOOPSTART_CODE 0x2E
#define AL_CMIDI_LOOPEND_CODE 0x2D
#define AL_CMIDI_CNTRL_LOOPSTART 102
#define AL_CMIDI_CNTRL_LOOPEND 103
#define AL_CMIDI_CNTRL_LOOPCOUNT_SM 104
#define AL_CMIDI_CNTRL_LOOPCOUNT_BIG 105
#define AL_PHASE_ATTACK 0
#define AL_PHASE_NOTEON 0
#define AL_PHASE_DECAY 1
#define AL_PHASE_SUSTAIN 2
#define AL_PHASE_RELEASE 3
#define AL_PHASE_SUSTREL 4
#define NO_SOUND_ERR_MASK 0x01
#define NOTE_OFF_ERR_MASK 0x02
#define NO_VOICE_ERR_MASK 0x04
#define alSeqpSetProgram alSeqpSetChlProgram
#define alSeqpGetProgram alSeqpGetChlProgram
#define alSeqpSetFXMix alSeqpSetChlFXMix
#define alSeqpGetFXMix alSeqpGetChlFXMix
#define alSeqpSetPan alSeqpSetChlPan
#define alSeqpGetPan alSeqpGetChlPan
#define alSeqpSetChannelPriority alSeqpSetChlPriority
#define alSeqpGetChannelPriority alSeqpGetChlPriority
#define alCSPSetProgram alCSPSetChlProgram
#define alCSPGetProgram alCSPGetChlProgram
#define alCSPSetFXMix alCSPSetChlFXMix
#define alCSPGetFXMix alCSPGetChlFXMix
#define alCSPSetPan alCSPSetChlPan
#define alCSPGetPan alCSPGetChlPan
#define alCSPSetChannelPriority alCSPSetChlPriority
#define alCSPGetChannelPriority alCSPGetChlPriority
#define _OS_H_ 
#define _OS_TIME_H_ 
#define _OS_MESSAGE_H_ 
#define _OS_THREAD_H_ 
#define OS_STATE_STOPPED (1 << 0)
#define OS_STATE_RUNNABLE (1 << 1)
#define OS_STATE_RUNNING (1 << 2)
#define OS_STATE_WAITING (1 << 3)
#define OS_PRIORITY_MAX 255
#define OS_PRIORITY_VIMGR 254
#define OS_PRIORITY_RMON 250
#define OS_PRIORITY_RMONSPIN 200
#define OS_PRIORITY_PIMGR 150
#define OS_PRIORITY_SIMGR 140
#define OS_PRIORITY_APPMAX 127
#define OS_PRIORITY_IDLE 0
#define THPROF_IDMAX 64
#define THPROF_STACKSIZE 256
#define OS_NUM_EVENTS 23
#define OS_EVENT_SW1 0
#define OS_EVENT_SW2 1
#define OS_EVENT_CART 2
#define OS_EVENT_COUNTER 3
#define OS_EVENT_SP 4
#define OS_EVENT_SI 5
#define OS_EVENT_AI 6
#define OS_EVENT_VI 7
#define OS_EVENT_PI 8
#define OS_EVENT_DP 9
#define OS_EVENT_CPU_BREAK 10
#define OS_EVENT_SP_BREAK 11
#define OS_EVENT_FAULT 12
#define OS_EVENT_THREADSTATUS 13
#define OS_EVENT_PRENMI 14
#define OS_EVENT_RDB_READ_DONE 15
#define OS_EVENT_RDB_LOG_DONE 16
#define OS_EVENT_RDB_DATA_DONE 17
#define OS_EVENT_RDB_REQ_RAMROM 18
#define OS_EVENT_RDB_FREE_RAMROM 19
#define OS_EVENT_RDB_DBG_DONE 20
#define OS_EVENT_RDB_FLUSH_PROF 21
#define OS_EVENT_RDB_ACK_PROF 22
#define OS_MESG_NOBLOCK 0
#define OS_MESG_BLOCK 1
#define MQ_GET_COUNT(mq) ((mq)->validCount)
#define MQ_IS_EMPTY(mq) (MQ_GET_COUNT(mq) == 0)
#define MQ_IS_FULL(mq) (MQ_GET_COUNT(mq) >= (mq)->msgCount)
#define _OS_AI_H_ 
#define _OS_CACHE_H_ 
#define OS_DCACHE_ROUNDUP_ADDR(x) (void*) (((((u32) (x) + 0xf) / 0x10) * 0x10))
#define OS_DCACHE_ROUNDUP_SIZE(x) (u32)(((((u32) (x) + 0xf) / 0x10) * 0x10))
#define _OS_CONT_H_ 
#define MAXCONTROLLERS 4
#define CONT_NO_RESPONSE_ERROR 0x8
#define CONT_OVERRUN_ERROR 0x4
#define CONT_RANGE_ERROR -1
#define CONT_ABSOLUTE 0x0001
#define CONT_RELATIVE 0x0002
#define CONT_JOYPORT 0x0004
#define CONT_EEPROM 0x8000
#define CONT_EEP16K 0x4000
#define CONT_TYPE_MASK 0x1f07
#define CONT_TYPE_NORMAL 0x0005
#define CONT_TYPE_MOUSE 0x0002
#define CONT_TYPE_VOICE 0x0100
#define CONT_CARD_ON 0x01
#define CONT_CARD_PULL 0x02
#define CONT_ADDR_CRC_ER 0x04
#define CONT_EEPROM_BUSY 0x80
#define CONT_A 0x8000
#define CONT_B 0x4000
#define CONT_G 0x2000
#define CONT_START 0x1000
#define CONT_UP 0x0800
#define CONT_DOWN 0x0400
#define CONT_LEFT 0x0200
#define CONT_RIGHT 0x0100
#define CONT_L 0x0020
#define CONT_R 0x0010
#define CONT_E 0x0008
#define CONT_D 0x0004
#define CONT_C 0x0002
#define CONT_F 0x0001
#define A_BUTTON CONT_A
#define B_BUTTON CONT_B
#define L_TRIG CONT_L
#define R_TRIG CONT_R
#define Z_TRIG CONT_G
#define START_BUTTON CONT_START
#define U_JPAD CONT_UP
#define L_JPAD CONT_LEFT
#define R_JPAD CONT_RIGHT
#define D_JPAD CONT_DOWN
#define U_CBUTTONS CONT_E
#define L_CBUTTONS CONT_C
#define R_CBUTTONS CONT_F
#define D_CBUTTONS CONT_D
#define RECENTER_BUTTON 0x0080
#define CONT_ERR_NO_CONTROLLER PFS_ERR_NOPACK
#define CONT_ERR_CONTRFAIL CONT_OVERRUN_ERROR
#define CONT_ERR_INVALID PFS_ERR_INVALID
#define CONT_ERR_DEVICE PFS_ERR_DEVICE
#define CONT_ERR_NOT_READY 12
#define CONT_ERR_VOICE_MEMORY 13
#define CONT_ERR_VOICE_WORD 14
#define CONT_ERR_VOICE_NO_RESPONSE 15
#define _OS_CONVERT_H_ 
#define OS_CLOCK_RATE 62500000LL
#define OS_CPU_COUNTER (OS_CLOCK_RATE * 3 / 4)
#define OS_NSEC_TO_CYCLES(n) (((u64) (n) * (OS_CPU_COUNTER / 15625000LL)) / (1000000000LL / 15625000LL))
#define OS_USEC_TO_CYCLES(n) (((u64) (n) * (OS_CPU_COUNTER / 15625LL)) / (1000000LL / 15625LL))
#define OS_CYCLES_TO_NSEC(c) (((u64) (c) * (1000000000LL / 15625000LL)) / (OS_CPU_COUNTER / 15625000LL))
#define OS_CYCLES_TO_USEC(c) (((u64) (c) * (1000000LL / 15625LL)) / (OS_CPU_COUNTER / 15625LL))
#define OS_K0_TO_PHYSICAL(x) (u32)(((char*) (x) -0x80000000))
#define OS_K1_TO_PHYSICAL(x) (u32)(((char*) (x) -0xa0000000))
#define OS_PHYSICAL_TO_K0(x) (void*) (((u32) (x) + 0x80000000))
#define OS_PHYSICAL_TO_K1(x) (void*) (((u32) (x) + 0xa0000000))
#define _OS_DEBUG_H_ 
#define PROF_MIN_INTERVAL 50
#define _OS_EEPROM_H_ 
#define EEPROM_TYPE_4K 0x01
#define EEPROM_TYPE_16K 0x02
#define EEPROM_MAXBLOCKS 64
#define EEP16K_MAXBLOCKS 256
#define EEPROM_BLOCK_SIZE 8
#define _OS_ERROR_H_ 
#define _OS_EXCEPTION_H_ 
#define OS_FLAG_CPU_BREAK 1
#define OS_FLAG_FAULT 2
#define OS_IM_NONE 0x00000001
#define OS_IM_RCP 0x00000401
#define OS_IM_SW1 0x00000501
#define OS_IM_SW2 0x00000601
#define OS_IM_CART 0x00000c01
#define OS_IM_PRENMI 0x00001401
#define OS_IM_RDBWRITE 0x00002401
#define OS_IM_RDBREAD 0x00004401
#define OS_IM_COUNTER 0x00008401
#define OS_IM_CPU 0x0000ff01
#define OS_IM_SP 0x00010401
#define OS_IM_SI 0x00020401
#define OS_IM_AI 0x00040401
#define OS_IM_VI 0x00080401
#define OS_IM_PI 0x00100401
#define OS_IM_DP 0x00200401
#define OS_IM_ALL 0x003fff01
#define RCP_IMASK 0x003f0000
#define RCP_IMASKSHIFT 16
#define _OS_FLASH_H_ 
#define _OS_PI_H_ 
#define OS_READ 0
#define OS_WRITE 1
#define OS_OTHERS 2
#define OS_MESG_TYPE_BASE (10)
#define OS_MESG_TYPE_LOOPBACK (OS_MESG_TYPE_BASE + 0)
#define OS_MESG_TYPE_DMAREAD (OS_MESG_TYPE_BASE + 1)
#define OS_MESG_TYPE_DMAWRITE (OS_MESG_TYPE_BASE + 2)
#define OS_MESG_TYPE_VRETRACE (OS_MESG_TYPE_BASE + 3)
#define OS_MESG_TYPE_COUNTER (OS_MESG_TYPE_BASE + 4)
#define OS_MESG_TYPE_EDMAREAD (OS_MESG_TYPE_BASE + 5)
#define OS_MESG_TYPE_EDMAWRITE (OS_MESG_TYPE_BASE + 6)
#define OS_MESG_PRI_NORMAL 0
#define OS_MESG_PRI_HIGH 1
#define PI_DOMAIN1 0
#define PI_DOMAIN2 1
#define FLASH_START_ADDR 0x08000000
#define FLASH_SIZE 0x20000
#define FLASH_LATENCY 0x5
#define FLASH_PULSE 0x0c
#define FLASH_PAGE_SIZE 0xf
#define FLASH_REL_DURATION 0x2
#define DEVICE_TYPE_FLASH 8
#define FLASH_VERSION_MX_PROTO_A 0x00c20000
#define FLASH_VERSION_MX_A 0x00c20001
#define FLASH_VERSION_MX_C 0x00c2001e
#define FLASH_VERSION_MX_B_AND_D 0x00c2001d
#define FLASH_VERSION_MEI 0x003200f1
#define OLD_FLASH 0
#define NEW_FLASH 1
#define FLASH_STATUS_ERASE_BUSY 2
#define FLASH_STATUS_ERASE_OK 0
#define FLASH_STATUS_ERASE_ERROR -1
#define FLASH_STATUS_WRITE_BUSY 1
#define FLASH_STATUS_WRITE_OK 0
#define FLASH_STATUS_WRITE_ERROR -1
#define _OS_GBPAK_H_ 
#define _OS_PFS_H_ 
#define OS_PFS_VERSION 0x0200
#define OS_PFS_VERSION_HI (OS_PFS_VERSION >> 8)
#define OS_PFS_VERSION_LO (OS_PFS_VERSION & 255)
#define PFS_INODE_SIZE_PER_PAGE 128
#define PFS_FILE_NAME_LEN 16
#define PFS_FILE_EXT_LEN 4
#define BLOCKSIZE 32
#define PFS_ONE_PAGE 8
#define PFS_MAX_BANKS 62
#define PFS_READ 0
#define PFS_WRITE 1
#define PFS_CREATE 2
#define PFS_INITIALIZED 0x1
#define PFS_CORRUPTED 0x2
#define PFS_ID_BROKEN 0x4
#define PFS_MOTOR_INITIALIZED 0x8
#define PFS_GBPAK_INITIALIZED 0x10
#define PFS_EOF 1
#define PFS_PAGE_NOT_EXIST 2
#define PFS_PAGE_NOT_USED 3
#define PFS_ERR_NOPACK 1
#define PFS_ERR_NEW_PACK 2
#define PFS_ERR_INCONSISTENT 3
#define PFS_ERR_CONTRFAIL CONT_OVERRUN_ERROR
#define PFS_ERR_INVALID 5
#define PFS_ERR_BAD_DATA 6
#define PFS_DATA_FULL 7
#define PFS_DIR_FULL 8
#define PFS_ERR_EXIST 9
#define PFS_ERR_ID_FATAL 10
#define PFS_ERR_DEVICE 11
#define PFS_ERR_NO_GBCART 12
#define PFS_ERR_NEW_GBCART 13
#define PFS_ID_BANK_256K 0
#define PFS_ID_BANK_1M 4
#define PFS_BANKS_256K 1
#define PFS_WRITTEN 2
#define DEF_DIR_PAGES 2
#define PFS_ID_0AREA 1
#define PFS_ID_1AREA 3
#define PFS_ID_2AREA 4
#define PFS_ID_3AREA 6
#define PFS_LABEL_AREA 7
#define PFS_ID_PAGE PFS_ONE_PAGE * 0
#define PFS_BANK_LAPPED_BY 8
#define PFS_SECTOR_PER_BANK 32
#define PFS_INODE_DIST_MAP (PFS_BANK_LAPPED_BY * PFS_SECTOR_PER_BANK)
#define PFS_SECTOR_SIZE (PFS_INODE_SIZE_PER_PAGE / PFS_SECTOR_PER_BANK)
#define OS_GBPAK_POWER 0x01
#define OS_GBPAK_RSTB_DETECTION 0x04
#define OS_GBPAK_RSTB_STATUS 0x08
#define OS_GBPAK_GBCART_PULL 0x40
#define OS_GBPAK_GBCART_ON 0x80
#define OS_GBPAK_POWER_OFF 0x00
#define OS_GBPAK_POWER_ON 0x01
#define OS_GBPAK_ROM_ID_SIZE 0x50
#define _OS_GIO_H_ 
#define _OS_HOST_H_ 
#define _OS_LIBC_H_ 
#define _OS_MOTOR_H_ 
#define _OS_RDP_H_ 
#define _OS_REG_H_ 
#define _OS_RSP_H_ 
#define _OS_SI_H_ 
#define _OS_SYSTEM_H_ 
#define OS_TV_PAL 0
#define OS_TV_NTSC 1
#define OS_TV_MPAL 2
#define OS_APP_NMI_BUFSIZE 64
#define _OS_TLB_H_ 
#define OS_PM_4K 0x0000000
#define OS_PM_16K 0x0006000
#define OS_PM_64K 0x001e000
#define OS_PM_256K 0x007e000
#define OS_PM_1M 0x01fe000
#define OS_PM_4M 0x07fe000
#define OS_PM_16M 0x1ffe000
#define _OS_VI_H_ 
#define OS_VI_NTSC_LPN1 0
#define OS_VI_NTSC_LPF1 1
#define OS_VI_NTSC_LAN1 2
#define OS_VI_NTSC_LAF1 3
#define OS_VI_NTSC_LPN2 4
#define OS_VI_NTSC_LPF2 5
#define OS_VI_NTSC_LAN2 6
#define OS_VI_NTSC_LAF2 7
#define OS_VI_NTSC_HPN1 8
#define OS_VI_NTSC_HPF1 9
#define OS_VI_NTSC_HAN1 10
#define OS_VI_NTSC_HAF1 11
#define OS_VI_NTSC_HPN2 12
#define OS_VI_NTSC_HPF2 13
#define OS_VI_PAL_LPN1 14
#define OS_VI_PAL_LPF1 15
#define OS_VI_PAL_LAN1 16
#define OS_VI_PAL_LAF1 17
#define OS_VI_PAL_LPN2 18
#define OS_VI_PAL_LPF2 19
#define OS_VI_PAL_LAN2 20
#define OS_VI_PAL_LAF2 21
#define OS_VI_PAL_HPN1 22
#define OS_VI_PAL_HPF1 23
#define OS_VI_PAL_HAN1 24
#define OS_VI_PAL_HAF1 25
#define OS_VI_PAL_HPN2 26
#define OS_VI_PAL_HPF2 27
#define OS_VI_MPAL_LPN1 28
#define OS_VI_MPAL_LPF1 29
#define OS_VI_MPAL_LAN1 30
#define OS_VI_MPAL_LAF1 31
#define OS_VI_MPAL_LPN2 32
#define OS_VI_MPAL_LPF2 33
#define OS_VI_MPAL_LAN2 34
#define OS_VI_MPAL_LAF2 35
#define OS_VI_MPAL_HPN1 36
#define OS_VI_MPAL_HPF1 37
#define OS_VI_MPAL_HAN1 38
#define OS_VI_MPAL_HAF1 39
#define OS_VI_MPAL_HPN2 40
#define OS_VI_MPAL_HPF2 41
#define OS_VI_FPAL_LPN1 42
#define OS_VI_FPAL_LPF1 43
#define OS_VI_FPAL_LAN1 44
#define OS_VI_FPAL_LAF1 45
#define OS_VI_FPAL_LPN2 46
#define OS_VI_FPAL_LPF2 47
#define OS_VI_FPAL_LAN2 48
#define OS_VI_FPAL_LAF2 49
#define OS_VI_FPAL_HPN1 50
#define OS_VI_FPAL_HPF1 51
#define OS_VI_FPAL_HAN1 52
#define OS_VI_FPAL_HAF1 53
#define OS_VI_FPAL_HPN2 54
#define OS_VI_FPAL_HPF2 55
#define OS_VI_GAMMA_ON 0x0001
#define OS_VI_GAMMA_OFF 0x0002
#define OS_VI_GAMMA_DITHER_ON 0x0004
#define OS_VI_GAMMA_DITHER_OFF 0x0008
#define OS_VI_DIVOT_ON 0x0010
#define OS_VI_DIVOT_OFF 0x0020
#define OS_VI_DITHER_FILTER_ON 0x0040
#define OS_VI_DITHER_FILTER_OFF 0x0080
#define OS_VI_BIT_NONINTERLACE 0x0001
#define OS_VI_BIT_INTERLACE 0x0002
#define OS_VI_BIT_NORMALINTERLACE 0x0004
#define OS_VI_BIT_DEFLICKINTERLACE 0x0008
#define OS_VI_BIT_ANTIALIAS 0x0010
#define OS_VI_BIT_POINTSAMPLE 0x0020
#define OS_VI_BIT_16PIXEL 0x0040
#define OS_VI_BIT_32PIXEL 0x0080
#define OS_VI_BIT_LORES 0x0100
#define OS_VI_BIT_HIRES 0x0200
#define OS_VI_BIT_NTSC 0x0400
#define OS_VI_BIT_PAL 0x0800
#define _OS_VOICE_H_ 
#define VOICE_WARN_TOO_SMALL 0x0400
#define VOICE_WARN_TOO_LARGE 0x0800
#define VOICE_WARN_NOT_FIT 0x4000
#define VOICE_WARN_TOO_NOISY 0x8000
#define VOICE_STATUS_READY 0
#define VOICE_STATUS_START 1
#define VOICE_STATUS_CANCEL 3
#define VOICE_STATUS_BUSY 5
#define VOICE_STATUS_END 7
#define OS_PIM_STACKSIZE 4096
#define OS_VIM_STACKSIZE 4096
#define OS_SIM_STACKSIZE 4096
#define OS_MIN_STACKSIZE 72
#define LEO_BLOCK_MODE 1
#define LEO_TRACK_MODE 2
#define LEO_SECTOR_MODE 3
#define BOOT_ADDRESS_ULTRA 0x80000400
#define BOOT_ADDRESS_COSIM 0x80002000
#define BOOT_ADDRESS_EMU 0x20010000
#define BOOT_ADDRESS_INDY 0x88100000
#define _RAMROM_H 
#define RAMROM_SIZE (0x1000000)
#define RAMROM_BUF_SIZE (4096)
#define RAMROM_MSG_SIZE (RAMROM_BUF_SIZE * 6)
#define RAMROM_MSG_ADDR (RAMROM_SIZE - RAMROM_MSG_SIZE)
#define RAMROM_MSG_HDR_SIZE (3 * sizeof(long))
#define RAMROM_USER_DATA_SIZE (RAMROM_MSG_SIZE - RAMROM_MSG_HDR_SIZE)
#define RAMROM_APP_READ_ADDR (RAMROM_MSG_ADDR + (0 * RAMROM_BUF_SIZE))
#define RAMROM_APP_WRITE_ADDR (RAMROM_MSG_ADDR + (1 * RAMROM_BUF_SIZE))
#define RAMROM_RMON_READ_ADDR (RAMROM_MSG_ADDR + (2 * RAMROM_BUF_SIZE))
#define RAMROM_RMON_WRITE_ADDR (RAMROM_MSG_ADDR + (3 * RAMROM_BUF_SIZE))
#define RAMROM_PRINTF_ADDR (RAMROM_MSG_ADDR + (4 * RAMROM_BUF_SIZE))
#define RAMROM_LOG_ADDR (RAMROM_MSG_ADDR + (5 * RAMROM_BUF_SIZE))
#define RAMROM_BOOTSTRAP_OFFSET 0x40
#define RAMROM_GAME_OFFSET 0x1000
#define RAMROM_FONTDATA_OFFSET 0xb70
#define RAMROM_FONTDATA_SIZE 1152
#define RAMROM_CLOCKRATE_OFFSET 0x4
#define RAMROM_CLOCKRATE_MASK 0xfffffff0
#define RAMROM_BOOTADDR_OFFSET 0x8
#define RAMROM_RELEASE_OFFSET 0xc
#define RAMROM_PIF2BOOTSTRAP_OFFSET 0x1000
#define HOST_PIACCESS_REQ 1
#define HOST_DBG_CMD_READY 2
#define GAME_DBG_DATA_SEND 3
#define HOST_DBG_DATA_ACK 4
#define GAME_PRINTF_SEND 5
#define HOST_PRINTF_ACK 6
#define GAME_LOG_SEND 7
#define HOST_LOG_ACK 8
#define HOST_APP_CMD_READY 9
#define GAME_APP_DATA_READY 10
#define HOST_PROF_REQ 11
#define GAME_PROF_SEND 12
#define HOST_PROF_ACK 13
#define GAME_FAULT_SEND 14
#define HOST_FAULT_ACK 15
#define GAME_EXIT 16
#define HOST_DATA_ACK 17
#define _RCP_H_ 
#define __R4300_H__ 
#define KUBASE 0
#define KUSIZE 0x80000000
#define K0BASE 0x80000000
#define K0SIZE 0x20000000
#define K1BASE 0xA0000000
#define K1SIZE 0x20000000
#define K2BASE 0xC0000000
#define K2SIZE 0x20000000
#define SIZE_EXCVEC 0x80
#define UT_VEC K0BASE
#define R_VEC (K1BASE + 0x1fc00000)
#define XUT_VEC (K0BASE + 0x80)
#define ECC_VEC (K0BASE + 0x100)
#define E_VEC (K0BASE + 0x180)
#define K0_TO_K1(x) ((u32) (x) | 0xA0000000)
#define K1_TO_K0(x) ((u32) (x) & 0x9FFFFFFF)
#define K0_TO_PHYS(x) ((u32) (x) & 0x1FFFFFFF)
#define K1_TO_PHYS(x) ((u32) (x) & 0x1FFFFFFF)
#define KDM_TO_PHYS(x) ((u32) (x) & 0x1FFFFFFF)
#define PHYS_TO_K0(x) ((u32) (x) | 0x80000000)
#define PHYS_TO_K1(x) ((u32) (x) | 0xA0000000)
#define IS_KSEG0(x) ((u32) (x) >= K0BASE && (u32) (x) < K1BASE)
#define IS_KSEG1(x) ((u32) (x) >= K1BASE && (u32) (x) < K2BASE)
#define IS_KSEGDM(x) ((u32) (x) >= K0BASE && (u32) (x) < K2BASE)
#define IS_KSEG2(x) ((u32) (x) >= K2BASE && (u32) (x) < KPTE_SHDUBASE)
#define IS_KPTESEG(x) ((u32) (x) >= KPTE_SHDUBASE)
#define IS_KUSEG(x) ((u32) (x) < K0BASE)
#define NTLBENTRIES 31
#define TLBHI_VPN2MASK 0xffffe000
#define TLBHI_VPN2SHIFT 13
#define TLBHI_PIDMASK 0xff
#define TLBHI_PIDSHIFT 0
#define TLBHI_NPID 255
#define TLBLO_PFNMASK 0x3fffffc0
#define TLBLO_PFNSHIFT 6
#define TLBLO_CACHMASK 0x38
#define TLBLO_CACHSHIFT 3
#define TLBLO_UNCACHED 0x10
#define TLBLO_NONCOHRNT 0x18
#define TLBLO_EXLWR 0x28
#define TLBLO_D 0x4
#define TLBLO_V 0x2
#define TLBLO_G 0x1
#define TLBINX_PROBE 0x80000000
#define TLBINX_INXMASK 0x3f
#define TLBINX_INXSHIFT 0
#define TLBRAND_RANDMASK 0x3f
#define TLBRAND_RANDSHIFT 0
#define TLBWIRED_WIREDMASK 0x3f
#define TLBCTXT_BASEMASK 0xff800000
#define TLBCTXT_BASESHIFT 23
#define TLBCTXT_BASEBITS 9
#define TLBCTXT_VPNMASK 0x7ffff0
#define TLBCTXT_VPNSHIFT 4
#define TLBPGMASK_4K 0x0
#define TLBPGMASK_16K 0x6000
#define TLBPGMASK_64K 0x1e000
#define SR_CUMASK 0xf0000000
#define SR_CU3 0x80000000
#define SR_CU2 0x40000000
#define SR_CU1 0x20000000
#define SR_CU0 0x10000000
#define SR_RP 0x08000000
#define SR_FR 0x04000000
#define SR_RE 0x02000000
#define SR_ITS 0x01000000
#define SR_BEV 0x00400000
#define SR_TS 0x00200000
#define SR_SR 0x00100000
#define SR_CH 0x00040000
#define SR_CE 0x00020000
#define SR_DE 0x00010000
#define SR_IMASK 0x0000ff00
#define SR_IMASK8 0x00000000
#define SR_IMASK7 0x00008000
#define SR_IMASK6 0x0000c000
#define SR_IMASK5 0x0000e000
#define SR_IMASK4 0x0000f000
#define SR_IMASK3 0x0000f800
#define SR_IMASK2 0x0000fc00
#define SR_IMASK1 0x0000fe00
#define SR_IMASK0 0x0000ff00
#define SR_IBIT8 0x00008000
#define SR_IBIT7 0x00004000
#define SR_IBIT6 0x00002000
#define SR_IBIT5 0x00001000
#define SR_IBIT4 0x00000800
#define SR_IBIT3 0x00000400
#define SR_IBIT2 0x00000200
#define SR_IBIT1 0x00000100
#define SR_IMASKSHIFT 8
#define SR_KX 0x00000080
#define SR_SX 0x00000040
#define SR_UX 0x00000020
#define SR_KSU_MASK 0x00000018
#define SR_KSU_USR 0x00000010
#define SR_KSU_SUP 0x00000008
#define SR_KSU_KER 0x00000000
#define SR_ERL 0x00000004
#define SR_EXL 0x00000002
#define SR_IE 0x00000001
#define CAUSE_BD 0x80000000
#define CAUSE_CEMASK 0x30000000
#define CAUSE_CESHIFT 28
#define CAUSE_IP8 0x00008000
#define CAUSE_IP7 0x00004000
#define CAUSE_IP6 0x00002000
#define CAUSE_IP5 0x00001000
#define CAUSE_IP4 0x00000800
#define CAUSE_IP3 0x00000400
#define CAUSE_SW2 0x00000200
#define CAUSE_SW1 0x00000100
#define CAUSE_IPMASK 0x0000FF00
#define CAUSE_IPSHIFT 8
#define CAUSE_EXCMASK 0x0000007C
#define CAUSE_EXCSHIFT 2
#define EXC_CODE(x) ((x) << 2)
#define EXC_INT EXC_CODE(0)
#define EXC_MOD EXC_CODE(1)
#define EXC_RMISS EXC_CODE(2)
#define EXC_WMISS EXC_CODE(3)
#define EXC_RADE EXC_CODE(4)
#define EXC_WADE EXC_CODE(5)
#define EXC_IBE EXC_CODE(6)
#define EXC_DBE EXC_CODE(7)
#define EXC_SYSCALL EXC_CODE(8)
#define EXC_BREAK EXC_CODE(9)
#define EXC_II EXC_CODE(10)
#define EXC_CPU EXC_CODE(11)
#define EXC_OV EXC_CODE(12)
#define EXC_TRAP EXC_CODE(13)
#define EXC_VCEI EXC_CODE(14)
#define EXC_FPE EXC_CODE(15)
#define EXC_WATCH EXC_CODE(23)
#define EXC_VCED EXC_CODE(31)
#define C0_IMPMASK 0xff00
#define C0_IMPSHIFT 8
#define C0_REVMASK 0xff
#define C0_MAJREVMASK 0xf0
#define C0_MAJREVSHIFT 4
#define C0_MINREVMASK 0xf
#define C0_READI 0x1
#define C0_WRITEI 0x2
#define C0_WRITER 0x6
#define C0_PROBE 0x8
#define C0_RFE 0x10
#define CACH_PI 0x0
#define CACH_PD 0x1
#define CACH_SI 0x2
#define CACH_SD 0x3
#define C_IINV 0x0
#define C_IWBINV 0x0
#define C_ILT 0x4
#define C_IST 0x8
#define C_CDX 0xc
#define C_HINV 0x10
#define C_HWBINV 0x14
#define C_FILL 0x14
#define C_HWB 0x18
#define C_HSV 0x1c
#define ICACHE_SIZE 0x4000
#define ICACHE_LINESIZE 32
#define ICACHE_LINEMASK (ICACHE_LINESIZE - 1)
#define DCACHE_SIZE 0x2000
#define DCACHE_LINESIZE 16
#define DCACHE_LINEMASK (DCACHE_LINESIZE - 1)
#define CONFIG_CM 0x80000000
#define CONFIG_EC 0x70000000
#define CONFIG_EC_1_1 0x6
#define CONFIG_EC_3_2 0x7
#define CONFIG_EC_2_1 0x0
#define CONFIG_EC_3_1 0x1
#define CONFIG_EP 0x0f000000
#define CONFIG_SB 0x00c00000
#define CONFIG_SS 0x00200000
#define CONFIG_SW 0x00100000
#define CONFIG_EW 0x000c0000
#define CONFIG_SC 0x00020000
#define CONFIG_SM 0x00010000
#define CONFIG_BE 0x00008000
#define CONFIG_EM 0x00004000
#define CONFIG_EB 0x00002000
#define CONFIG_IC 0x00000e00
#define CONFIG_DC 0x000001c0
#define CONFIG_IB 0x00000020
#define CONFIG_DB 0x00000010
#define CONFIG_CU 0x00000008
#define CONFIG_K0 0x00000007
#define CONFIG_UNCACHED 0x00000002
#define CONFIG_NONCOHRNT 0x00000003
#define CONFIG_COHRNT_EXLWR 0x00000005
#define CONFIG_SB_SHFT 22
#define CONFIG_IC_SHFT 9
#define CONFIG_DC_SHFT 6
#define CONFIG_BE_SHFT 15
#define SADDRMASK 0xFFFFE000
#define SVINDEXMASK 0x00000380
#define SSTATEMASK 0x00001c00
#define SINVALID 0x00000000
#define SCLEANEXCL 0x00001000
#define SDIRTYEXCL 0x00001400
#define SECC_MASK 0x0000007f
#define SADDR_SHIFT 4
#define PADDRMASK 0xFFFFFF00
#define PADDR_SHIFT 4
#define PSTATEMASK 0x00C0
#define PINVALID 0x0000
#define PCLEANEXCL 0x0080
#define PDIRTYEXCL 0x00C0
#define PPARITY_MASK 0x0001
#define CACHERR_ER 0x80000000
#define CACHERR_EC 0x40000000
#define CACHERR_ED 0x20000000
#define CACHERR_ET 0x10000000
#define CACHERR_ES 0x08000000
#define CACHERR_EE 0x04000000
#define CACHERR_EB 0x02000000
#define CACHERR_EI 0x01000000
#define CACHERR_SIDX_MASK 0x003ffff8
#define CACHERR_PIDX_MASK 0x00000007
#define CACHERR_PIDX_SHIFT 12
#define WATCHLO_WTRAP 0x00000001
#define WATCHLO_RTRAP 0x00000002
#define WATCHLO_ADDRMASK 0xfffffff8
#define WATCHLO_VALIDMASK 0xfffffffb
#define WATCHHI_VALIDMASK 0x0000000f
#define C0_INX 0
#define C0_RAND 1
#define C0_ENTRYLO0 2
#define C0_ENTRYLO1 3
#define C0_CONTEXT 4
#define C0_PAGEMASK 5
#define C0_WIRED 6
#define C0_BADVADDR 8
#define C0_COUNT 9
#define C0_ENTRYHI 10
#define C0_SR 12
#define C0_CAUSE 13
#define C0_EPC 14
#define C0_PRID 15
#define C0_COMPARE 11
#define C0_CONFIG 16
#define C0_LLADDR 17
#define C0_WATCHLO 18
#define C0_WATCHHI 19
#define C0_ECC 26
#define C0_CACHE_ERR 27
#define C0_TAGLO 28
#define C0_TAGHI 29
#define C0_ERROR_EPC 30
#define FPCSR_FS 0x01000000
#define FPCSR_C 0x00800000
#define FPCSR_CE 0x00020000
#define FPCSR_CV 0x00010000
#define FPCSR_CZ 0x00008000
#define FPCSR_CO 0x00004000
#define FPCSR_CU 0x00002000
#define FPCSR_CI 0x00001000
#define FPCSR_EV 0x00000800
#define FPCSR_EZ 0x00000400
#define FPCSR_EO 0x00000200
#define FPCSR_EU 0x00000100
#define FPCSR_EI 0x00000080
#define FPCSR_FV 0x00000040
#define FPCSR_FZ 0x00000020
#define FPCSR_FO 0x00000010
#define FPCSR_FU 0x00000008
#define FPCSR_FI 0x00000004
#define FPCSR_RM_MASK 0x00000003
#define FPCSR_RM_RN 0x00000000
#define FPCSR_RM_RZ 0x00000001
#define FPCSR_RM_RP 0x00000002
#define FPCSR_RM_RM 0x00000003
#define RDRAM_0_START 0x00000000
#define RDRAM_0_END 0x001FFFFF
#define RDRAM_1_START 0x00200000
#define RDRAM_1_END 0x003FFFFF
#define RDRAM_START RDRAM_0_START
#define RDRAM_END RDRAM_1_END
#define RDRAM_BASE_REG 0x03F00000
#define RDRAM_CONFIG_REG (RDRAM_BASE_REG + 0x00)
#define RDRAM_DEVICE_TYPE_REG (RDRAM_BASE_REG + 0x00)
#define RDRAM_DEVICE_ID_REG (RDRAM_BASE_REG + 0x04)
#define RDRAM_DELAY_REG (RDRAM_BASE_REG + 0x08)
#define RDRAM_MODE_REG (RDRAM_BASE_REG + 0x0c)
#define RDRAM_REF_INTERVAL_REG (RDRAM_BASE_REG + 0x10)
#define RDRAM_REF_ROW_REG (RDRAM_BASE_REG + 0x14)
#define RDRAM_RAS_INTERVAL_REG (RDRAM_BASE_REG + 0x18)
#define RDRAM_MIN_INTERVAL_REG (RDRAM_BASE_REG + 0x1c)
#define RDRAM_ADDR_SELECT_REG (RDRAM_BASE_REG + 0x20)
#define RDRAM_DEVICE_MANUF_REG (RDRAM_BASE_REG + 0x24)
#define RDRAM_0_DEVICE_ID 0
#define RDRAM_1_DEVICE_ID 1
#define RDRAM_RESET_MODE 0
#define RDRAM_ACTIVE_MODE 1
#define RDRAM_STANDBY_MODE 2
#define RDRAM_LENGTH (2 * 512 * 2048)
#define RDRAM_0_BASE_ADDRESS (RDRAM_0_DEVICE_ID * RDRAM_LENGTH)
#define RDRAM_1_BASE_ADDRESS (RDRAM_1_DEVICE_ID * RDRAM_LENGTH)
#define RDRAM_0_CONFIG 0x00000
#define RDRAM_1_CONFIG 0x00400
#define RDRAM_GLOBAL_CONFIG 0x80000
#define PIF_ROM_START 0x1FC00000
#define PIF_ROM_END 0x1FC007BF
#define PIF_RAM_START 0x1FC007C0
#define PIF_RAM_END 0x1FC007FF
#define CHNL_ERR_NORESP 0x80
#define CHNL_ERR_OVERRUN 0x40
#define CHNL_ERR_FRAME 0x80
#define CHNL_ERR_COLLISION 0x40
#define CHNL_ERR_MASK 0xC0
#define DEVICE_TYPE_CART 0
#define DEVICE_TYPE_BULK 1
#define DEVICE_TYPE_64DD 2
#define DEVICE_TYPE_SRAM 3
#define DEVICE_TYPE_INIT 7
#define SP_DMEM_START 0x04000000
#define SP_DMEM_END 0x04000FFF
#define SP_IMEM_START 0x04001000
#define SP_IMEM_END 0x04001FFF
#define SP_BASE_REG 0x04040000
#define SP_MEM_ADDR_REG (SP_BASE_REG + 0x00)
#define SP_DRAM_ADDR_REG (SP_BASE_REG + 0x04)
#define SP_RD_LEN_REG (SP_BASE_REG + 0x08)
#define SP_WR_LEN_REG (SP_BASE_REG + 0x0C)
#define SP_STATUS_REG (SP_BASE_REG + 0x10)
#define SP_DMA_FULL_REG (SP_BASE_REG + 0x14)
#define SP_DMA_BUSY_REG (SP_BASE_REG + 0x18)
#define SP_SEMAPHORE_REG (SP_BASE_REG + 0x1C)
#define SP_PC_REG 0x04080000
#define SP_DMA_DMEM (0 << 12)
#define SP_DMA_IMEM (1 << 12)
#define SP_CLR_HALT (1 << 0)
#define SP_SET_HALT (1 << 1)
#define SP_CLR_BROKE (1 << 2)
#define SP_CLR_INTR (1 << 3)
#define SP_SET_INTR (1 << 4)
#define SP_CLR_SSTEP (1 << 5)
#define SP_SET_SSTEP (1 << 6)
#define SP_CLR_INTR_BREAK (1 << 7)
#define SP_SET_INTR_BREAK (1 << 8)
#define SP_CLR_SIG0 (1 << 9)
#define SP_SET_SIG0 (1 << 10)
#define SP_CLR_SIG1 (1 << 11)
#define SP_SET_SIG1 (1 << 12)
#define SP_CLR_SIG2 (1 << 13)
#define SP_SET_SIG2 (1 << 14)
#define SP_CLR_SIG3 (1 << 15)
#define SP_SET_SIG3 (1 << 16)
#define SP_CLR_SIG4 (1 << 17)
#define SP_SET_SIG4 (1 << 18)
#define SP_CLR_SIG5 (1 << 19)
#define SP_SET_SIG5 (1 << 20)
#define SP_CLR_SIG6 (1 << 21)
#define SP_SET_SIG6 (1 << 22)
#define SP_CLR_SIG7 (1 << 23)
#define SP_SET_SIG7 (1 << 24)
#define SP_STATUS_HALT (1 << 0)
#define SP_STATUS_BROKE (1 << 1)
#define SP_STATUS_DMA_BUSY (1 << 2)
#define SP_STATUS_DMA_FULL (1 << 3)
#define SP_STATUS_IO_FULL (1 << 4)
#define SP_STATUS_SSTEP (1 << 5)
#define SP_STATUS_INTR_BREAK (1 << 6)
#define SP_STATUS_SIG0 (1 << 7)
#define SP_STATUS_SIG1 (1 << 8)
#define SP_STATUS_SIG2 (1 << 9)
#define SP_STATUS_SIG3 (1 << 10)
#define SP_STATUS_SIG4 (1 << 11)
#define SP_STATUS_SIG5 (1 << 12)
#define SP_STATUS_SIG6 (1 << 13)
#define SP_STATUS_SIG7 (1 << 14)
#define SP_CLR_YIELD SP_CLR_SIG0
#define SP_SET_YIELD SP_SET_SIG0
#define SP_STATUS_YIELD SP_STATUS_SIG0
#define SP_CLR_YIELDED SP_CLR_SIG1
#define SP_SET_YIELDED SP_SET_SIG1
#define SP_STATUS_YIELDED SP_STATUS_SIG1
#define SP_CLR_TASKDONE SP_CLR_SIG2
#define SP_SET_TASKDONE SP_SET_SIG2
#define SP_STATUS_TASKDONE SP_STATUS_SIG2
#define SP_CLR_RSPSIGNAL SP_CLR_SIG3
#define SP_SET_RSPSIGNAL SP_SET_SIG3
#define SP_STATUS_RSPSIGNAL SP_STATUS_SIG3
#define SP_CLR_CPUSIGNAL SP_CLR_SIG4
#define SP_SET_CPUSIGNAL SP_SET_SIG4
#define SP_STATUS_CPUSIGNAL SP_STATUS_SIG4
#define SP_IBIST_REG 0x04080004
#define SP_IBIST_CHECK (1 << 0)
#define SP_IBIST_GO (1 << 1)
#define SP_IBIST_CLEAR (1 << 2)
#define SP_IBIST_DONE (1 << 2)
#define SP_IBIST_FAILED 0x78
#define DPC_BASE_REG 0x04100000
#define DPC_START_REG (DPC_BASE_REG + 0x00)
#define DPC_END_REG (DPC_BASE_REG + 0x04)
#define DPC_CURRENT_REG (DPC_BASE_REG + 0x08)
#define DPC_STATUS_REG (DPC_BASE_REG + 0x0C)
#define DPC_CLOCK_REG (DPC_BASE_REG + 0x10)
#define DPC_BUFBUSY_REG (DPC_BASE_REG + 0x14)
#define DPC_PIPEBUSY_REG (DPC_BASE_REG + 0x18)
#define DPC_TMEM_REG (DPC_BASE_REG + 0x1C)
#define DPC_CLR_XBUS_DMEM_DMA (1 << 0)
#define DPC_SET_XBUS_DMEM_DMA (1 << 1)
#define DPC_CLR_FREEZE (1 << 2)
#define DPC_SET_FREEZE (1 << 3)
#define DPC_CLR_FLUSH (1 << 4)
#define DPC_SET_FLUSH (1 << 5)
#define DPC_CLR_TMEM_CTR (1 << 6)
#define DPC_CLR_PIPE_CTR (1 << 7)
#define DPC_CLR_CMD_CTR (1 << 8)
#define DPC_CLR_CLOCK_CTR (1 << 9)
#define DPC_STATUS_XBUS_DMEM_DMA (1 << 0)
#define DPC_STATUS_FREEZE (1 << 1)
#define DPC_STATUS_FLUSH (1 << 2)
#define DPC_STATUS_START_GCLK (1 << 3)
#define DPC_STATUS_TMEM_BUSY (1 << 4)
#define DPC_STATUS_PIPE_BUSY (1 << 5)
#define DPC_STATUS_CMD_BUSY (1 << 6)
#define DPC_STATUS_CBUF_READY (1 << 7)
#define DPC_STATUS_DMA_BUSY (1 << 8)
#define DPC_STATUS_END_VALID (1 << 9)
#define DPC_STATUS_START_VALID (1 << 10)
#define DPS_BASE_REG 0x04200000
#define DPS_TBIST_REG (DPS_BASE_REG + 0x00)
#define DPS_TEST_MODE_REG (DPS_BASE_REG + 0x04)
#define DPS_BUFTEST_ADDR_REG (DPS_BASE_REG + 0x08)
#define DPS_BUFTEST_DATA_REG (DPS_BASE_REG + 0x0C)
#define DPS_TBIST_CHECK (1 << 0)
#define DPS_TBIST_GO (1 << 1)
#define DPS_TBIST_CLEAR (1 << 2)
#define DPS_TBIST_DONE (1 << 2)
#define DPS_TBIST_FAILED 0x7F8
#define MI_BASE_REG 0x04300000
#define MI_INIT_MODE_REG (MI_BASE_REG + 0x00)
#define MI_MODE_REG MI_INIT_MODE_REG
#define MI_CLR_INIT (1 << 7)
#define MI_SET_INIT (1 << 8)
#define MI_CLR_EBUS (1 << 9)
#define MI_SET_EBUS (1 << 10)
#define MI_CLR_DP_INTR (1 << 11)
#define MI_CLR_RDRAM (1 << 12)
#define MI_SET_RDRAM (1 << 13)
#define MI_MODE_INIT (1 << 7)
#define MI_MODE_EBUS (1 << 8)
#define MI_MODE_RDRAM (1 << 9)
#define MI_VERSION_REG (MI_BASE_REG + 0x04)
#define MI_NOOP_REG MI_VERSION_REG
#define MI_INTR_REG (MI_BASE_REG + 0x08)
#define MI_INTR_MASK_REG (MI_BASE_REG + 0x0C)
#define MI_INTR_SP (1 << 0)
#define MI_INTR_SI (1 << 1)
#define MI_INTR_AI (1 << 2)
#define MI_INTR_VI (1 << 3)
#define MI_INTR_PI (1 << 4)
#define MI_INTR_DP (1 << 5)
#define MI_INTR_MASK_CLR_SP (1 << 0)
#define MI_INTR_MASK_SET_SP (1 << 1)
#define MI_INTR_MASK_CLR_SI (1 << 2)
#define MI_INTR_MASK_SET_SI (1 << 3)
#define MI_INTR_MASK_CLR_AI (1 << 4)
#define MI_INTR_MASK_SET_AI (1 << 5)
#define MI_INTR_MASK_CLR_VI (1 << 6)
#define MI_INTR_MASK_SET_VI (1 << 7)
#define MI_INTR_MASK_CLR_PI (1 << 8)
#define MI_INTR_MASK_SET_PI (1 << 9)
#define MI_INTR_MASK_CLR_DP (1 << 10)
#define MI_INTR_MASK_SET_DP (1 << 11)
#define MI_INTR_MASK_SP (1 << 0)
#define MI_INTR_MASK_SI (1 << 1)
#define MI_INTR_MASK_AI (1 << 2)
#define MI_INTR_MASK_VI (1 << 3)
#define MI_INTR_MASK_PI (1 << 4)
#define MI_INTR_MASK_DP (1 << 5)
#define VI_BASE_REG 0x04400000
#define VI_CONTROL_REG (VI_BASE_REG + 0x00)
#define VI_STATUS_REG VI_CONTROL_REG
#define VI_ORIGIN_REG (VI_BASE_REG + 0x04)
#define VI_DRAM_ADDR_REG VI_ORIGIN_REG
#define VI_WIDTH_REG (VI_BASE_REG + 0x08)
#define VI_H_WIDTH_REG VI_WIDTH_REG
#define VI_INTR_REG (VI_BASE_REG + 0x0C)
#define VI_V_INTR_REG VI_INTR_REG
#define VI_CURRENT_REG (VI_BASE_REG + 0x10)
#define VI_V_CURRENT_LINE_REG VI_CURRENT_REG
#define VI_BURST_REG (VI_BASE_REG + 0x14)
#define VI_TIMING_REG VI_BURST_REG
#define VI_V_SYNC_REG (VI_BASE_REG + 0x18)
#define VI_H_SYNC_REG (VI_BASE_REG + 0x1C)
#define VI_LEAP_REG (VI_BASE_REG + 0x20)
#define VI_H_SYNC_LEAP_REG VI_LEAP_REG
#define VI_H_START_REG (VI_BASE_REG + 0x24)
#define VI_H_VIDEO_REG VI_H_START_REG
#define VI_V_START_REG (VI_BASE_REG + 0x28)
#define VI_V_VIDEO_REG VI_V_START_REG
#define VI_V_BURST_REG (VI_BASE_REG + 0x2C)
#define VI_X_SCALE_REG (VI_BASE_REG + 0x30)
#define VI_Y_SCALE_REG (VI_BASE_REG + 0x34)
#define VI_CTRL_TYPE_16 0x00002
#define VI_CTRL_TYPE_32 0x00003
#define VI_CTRL_GAMMA_DITHER_ON 0x00004
#define VI_CTRL_GAMMA_ON 0x00008
#define VI_CTRL_DIVOT_ON 0x00010
#define VI_CTRL_SERRATE_ON 0x00040
#define VI_CTRL_ANTIALIAS_MASK 0x00300
#define VI_CTRL_ANTIALIAS_MODE_1 0x00100
#define VI_CTRL_ANTIALIAS_MODE_2 0x00200
#define VI_CTRL_ANTIALIAS_MODE_3 0x00300
#define VI_CTRL_PIXEL_ADV_MASK 0x01000
#define VI_CTRL_PIXEL_ADV_1 0x01000
#define VI_CTRL_PIXEL_ADV_2 0x02000
#define VI_CTRL_PIXEL_ADV_3 0x03000
#define VI_CTRL_DITHER_FILTER_ON 0x10000
#define VI_NTSC_CLOCK 48681812
#define VI_PAL_CLOCK 49656530
#define VI_MPAL_CLOCK 48628316
#define AI_BASE_REG 0x04500000
#define AI_DRAM_ADDR_REG (AI_BASE_REG + 0x00)
#define AI_LEN_REG (AI_BASE_REG + 0x04)
#define AI_CONTROL_REG (AI_BASE_REG + 0x08)
#define AI_CONTROL_DMA_ON 1
#define AI_CONTROL_DMA_OFF 0
#define AI_STATUS_REG (AI_BASE_REG + 0x0C)
#define AI_STATUS_FIFO_FULL (1 << 31)
#define AI_STATUS_DMA_BUSY (1 << 30)
#define AI_DACRATE_REG (AI_BASE_REG + 0x10)
#define AI_MAX_DAC_RATE 16384
#define AI_MIN_DAC_RATE 132
#define AI_BITRATE_REG (AI_BASE_REG + 0x14)
#define AI_MAX_BIT_RATE 16
#define AI_MIN_BIT_RATE 2
#define AI_NTSC_MAX_FREQ 368000
#define AI_NTSC_MIN_FREQ 3000
#define AI_PAL_MAX_FREQ 376000
#define AI_PAL_MIN_FREQ 3050
#define AI_MPAL_MAX_FREQ 368000
#define AI_MPAL_MIN_FREQ 3000
#define PI_BASE_REG 0x04600000
#define PI_DRAM_ADDR_REG (PI_BASE_REG + 0x00)
#define PI_CART_ADDR_REG (PI_BASE_REG + 0x04)
#define PI_RD_LEN_REG (PI_BASE_REG + 0x08)
#define PI_WR_LEN_REG (PI_BASE_REG + 0x0C)
#define PI_STATUS_REG (PI_BASE_REG + 0x10)
#define PI_BSD_DOM1_LAT_REG (PI_BASE_REG + 0x14)
#define PI_BSD_DOM1_PWD_REG (PI_BASE_REG + 0x18)
#define PI_BSD_DOM1_PGS_REG (PI_BASE_REG + 0x1C)
#define PI_BSD_DOM1_RLS_REG (PI_BASE_REG + 0x20)
#define PI_BSD_DOM2_LAT_REG (PI_BASE_REG + 0x24)
#define PI_BSD_DOM2_PWD_REG (PI_BASE_REG + 0x28)
#define PI_BSD_DOM2_PGS_REG (PI_BASE_REG + 0x2C)
#define PI_BSD_DOM2_RLS_REG (PI_BASE_REG + 0x30)
#define PI_DOMAIN1_REG PI_BSD_DOM1_LAT_REG
#define PI_DOMAIN2_REG PI_BSD_DOM2_LAT_REG
#define PI_DOM_LAT_OFS 0x00
#define PI_DOM_PWD_OFS 0x04
#define PI_DOM_PGS_OFS 0x08
#define PI_DOM_RLS_OFS 0x0C
#define PI_STATUS_DMA_BUSY (1 << 0)
#define PI_STATUS_IO_BUSY (1 << 1)
#define PI_STATUS_ERROR (1 << 2)
#define PI_STATUS_RESET (1 << 0)
#define PI_SET_RESET PI_STATUS_RESET
#define PI_STATUS_CLR_INTR (1 << 1)
#define PI_CLR_INTR PI_STATUS_CLR_INTR
#define PI_DMA_BUFFER_SIZE 128
#define PI_DOM1_ADDR1 0x06000000
#define PI_DOM1_ADDR2 0x10000000
#define PI_DOM1_ADDR3 0x1FD00000
#define PI_DOM2_ADDR1 0x05000000
#define PI_DOM2_ADDR2 0x08000000
#define RI_BASE_REG 0x04700000
#define RI_MODE_REG (RI_BASE_REG + 0x00)
#define RI_CONFIG_REG (RI_BASE_REG + 0x04)
#define RI_CURRENT_LOAD_REG (RI_BASE_REG + 0x08)
#define RI_SELECT_REG (RI_BASE_REG + 0x0C)
#define RI_REFRESH_REG (RI_BASE_REG + 0x10)
#define RI_COUNT_REG RI_REFRESH_REG
#define RI_LATENCY_REG (RI_BASE_REG + 0x14)
#define RI_RERROR_REG (RI_BASE_REG + 0x18)
#define RI_WERROR_REG (RI_BASE_REG + 0x1C)
#define SI_BASE_REG 0x04800000
#define SI_DRAM_ADDR_REG (SI_BASE_REG + 0x00)
#define SI_PIF_ADDR_RD64B_REG (SI_BASE_REG + 0x04)
#define SI_PIF_ADDR_WR64B_REG (SI_BASE_REG + 0x10)
#define SI_STATUS_REG (SI_BASE_REG + 0x18)
#define SI_STATUS_DMA_BUSY (1 << 0)
#define SI_STATUS_RD_BUSY (1 << 1)
#define SI_STATUS_DMA_ERROR (1 << 3)
#define SI_STATUS_INTERRUPT (1 << 12)
#define GIO_BASE_REG 0x18000000
#define GIO_GIO_INTR_REG (GIO_BASE_REG + 0x000)
#define GIO_GIO_SYNC_REG (GIO_BASE_REG + 0x400)
#define GIO_CART_INTR_REG (GIO_BASE_REG + 0x800)
#define IO_READ(addr) (*(vu32*) PHYS_TO_K1(addr))
#define IO_WRITE(addr,data) (*(vu32*) PHYS_TO_K1(addr) = (u32) (data))
#define RCP_STAT_PRINT rmonPrintf("current=%x start=%x end=%x dpstat=%x spstat=%x\n", IO_READ(DPC_CURRENT_REG), IO_READ(DPC_START_REG), IO_READ(DPC_END_REG), IO_READ(DPC_STATUS_REG), IO_READ(SP_STATUS_REG))
#define _REGION_H_ 
#define ALIGNSZ (sizeof(long long))
#define ALIGNOFFST (ALIGNSZ - 1)
#define BUF_CTRL_SIZE ALIGNSZ
#define MAX_BUFCOUNT 0x8000
#define BUF_FREE_WO_NEXT 0x8000
#define OS_RG_ALIGN_2B 2
#define OS_RG_ALIGN_4B 4
#define OS_RG_ALIGN_8B 8
#define OS_RG_ALIGN_16B 16
#define OS_RG_ALIGN_DEFAULT OS_RG_ALIGN_8B
#define ALIGN(s,align) (((u32) (s) + ((align) -1)) & ~((align) -1))
#define RP(x) rp->r_##x
#define _RMON_H_ 
#define RMON_DBG_BUF_SIZE 2048
#define RMON_STACKSIZE 0x1000
#define _SP_H_ 
#define DL_BM_OVERHEAD (12)
#define DL_SPRITE_OVERHEAD (24)
#define NUM_DL(nb) ((nb) * DL_BM_OVERHEAD + DL_SPRITE_OVERHEAD)
#define SP_TRANSPARENT 0x00000001
#define SP_CUTOUT 0x00000002
#define SP_HIDDEN 0x00000004
#define SP_Z 0x00000008
#define SP_SCALE 0x00000010
#define SP_FASTCOPY 0x00000020
#define SP_OVERLAP 0x00000040
#define SP_TEXSHIFT 0x00000080
#define SP_FRACPOS 0x00000100
#define SP_TEXSHUF 0x00000200
#define SP_EXTERN 0x00000400
#define spMove spX2Move
#define spSetZ spX2SetZ
#define spScissor spX2Scissor
#define spDraw spX2Draw
#define spInit spX2Init
#define spFinish spX2Finish
#define _UCODE_H_ 
#define SP_DRAM_STACK_SIZE8 (1024)
#define SP_DRAM_STACK_SIZE64 (SP_DRAM_STACK_SIZE8 >> 3)
#define SP_UCODE_SIZE 4096
#define SP_UCODE_DATA_SIZE 2048
#define __ULTRAERROR_H__ 
#define OS_ERROR_FMT "/usr/lib/PR/error.fmt"
#define OS_ERROR_MAGIC 0x6b617479
#define ERR_OSCREATETHREAD_SP 1
#define ERR_OSCREATETHREAD_PRI 2
#define ERR_OSSTARTTHREAD 3
#define ERR_OSSETTHREADPRI 4
#define ERR_OSCREATEMESGQUEUE 5
#define ERR_OSSENDMESG 6
#define ERR_OSJAMMESG 7
#define ERR_OSRECVMESG 8
#define ERR_OSSETEVENTMESG 9
#define ERR_OSMAPTLB_INDEX 10
#define ERR_OSMAPTLB_ASID 11
#define ERR_OSUNMAPTLB 12
#define ERR_OSSETTLBASID 13
#define ERR_OSAISETFREQUENCY 14
#define ERR_OSAISETNEXTBUFFER_ADDR 15
#define ERR_OSAISETNEXTBUFFER_SIZE 16
#define ERR_OSDPSETNEXTBUFFER_ADDR 17
#define ERR_OSDPSETNEXTBUFFER_SIZE 18
#define ERR_OSPIRAWREADIO 19
#define ERR_OSPIRAWWRITEIO 20
#define ERR_OSPIRAWSTARTDMA_DIR 21
#define ERR_OSPIRAWSTARTDMA_DEVADDR 22
#define ERR_OSPIRAWSTARTDMA_ADDR 23
#define ERR_OSPIRAWSTARTDMA_SIZE 24
#define ERR_OSPIRAWSTARTDMA_RANGE 25
#define ERR_OSPIREADIO 26
#define ERR_OSPIWRITEIO 27
#define ERR_OSPISTARTDMA_PIMGR 28
#define ERR_OSPISTARTDMA_PRI 29
#define ERR_OSPISTARTDMA_DIR 30
#define ERR_OSPISTARTDMA_DEVADDR 31
#define ERR_OSPISTARTDMA_ADDR 32
#define ERR_OSPISTARTDMA_SIZE 33
#define ERR_OSPISTARTDMA_RANGE 34
#define ERR_OSCREATEPIMANAGER 35
#define ERR_OSVIGETCURRENTMODE 36
#define ERR_OSVIGETCURRENTFRAMEBUFFER 37
#define ERR_OSVIGETNEXTFRAMEBUFFER 38
#define ERR_OSVISETXSCALE_VALUE 39
#define ERR_OSVISETXSCALE_VIMGR 40
#define ERR_OSVISETYSCALE_VALUE 41
#define ERR_OSVISETYSCALE_VIMGR 42
#define ERR_OSVISETSPECIAL_VALUE 43
#define ERR_OSVISETSPECIAL_VIMGR 44
#define ERR_OSVISETMODE 45
#define ERR_OSVISETEVENT 46
#define ERR_OSVISWAPBUFFER_ADDR 47
#define ERR_OSVISWAPBUFFER_VIMGR 48
#define ERR_OSCREATEVIMANAGER 49
#define ERR_OSCREATEREGION_ALIGN 50
#define ERR_OSCREATEREGION_SIZE 51
#define ERR_OSMALLOC 52
#define ERR_OSFREE_REGION 53
#define ERR_OSFREE_ADDR 54
#define ERR_OSGETREGIONBUFCOUNT 55
#define ERR_OSGETREGIONBUFSIZE 56
#define ERR_OSSPTASKLOAD_DRAM 57
#define ERR_OSSPTASKLOAD_OUT 58
#define ERR_OSSPTASKLOAD_OUTSIZE 59
#define ERR_OSSPTASKLOAD_YIELD 60
#define ERR_OSPROFILEINIT_STR 61
#define ERR_OSPROFILEINIT_CNT 62
#define ERR_OSPROFILEINIT_ALN 63
#define ERR_OSPROFILEINIT_ORD 64
#define ERR_OSPROFILEINIT_SIZ 65
#define ERR_OSPROFILESTART_TIME 66
#define ERR_OSPROFILESTART_FLAG 67
#define ERR_OSPROFILESTOP_FLAG 68
#define ERR_OSPROFILESTOP_TIMER 69
#define ERR_OSREADHOST_ADDR 70
#define ERR_OSREADHOST_SIZE 71
#define ERR_OSWRITEHOST_ADDR 72
#define ERR_OSWRITEHOST_SIZE 73
#define ERR_OSGETTIME 74
#define ERR_OSSETTIME 75
#define ERR_OSSETTIMER 76
#define ERR_OSSTOPTIMER 77
#define ERR_ALSEQP_NO_SOUND 100
#define ERR_ALSEQP_NO_VOICE 101
#define ERR_ALSEQP_MAP_VOICE 102
#define ERR_ALSEQP_OFF_VOICE 103
#define ERR_ALSEQP_POLY_VOICE 104
#define ERR_ALSNDP_NO_VOICE 105
#define ERR_ALSYN_NO_UPDATE 106
#define ERR_ALSNDPDEALLOCATE 107
#define ERR_ALSNDPDELETE 108
#define ERR_ALSNDPPLAY 109
#define ERR_ALSNDPSETSOUND 110
#define ERR_ALSNDPSETPRIORITY 111
#define ERR_ALSNDPSETPAR 112
#define ERR_ALBNKFNEW 113
#define ERR_ALSEQNOTMIDI 114
#define ERR_ALSEQNOTMIDI0 115
#define ERR_ALSEQNUMTRACKS 116
#define ERR_ALSEQTIME 117
#define ERR_ALSEQTRACKHDR 118
#define ERR_ALSEQSYSEX 119
#define ERR_ALSEQMETA 120
#define ERR_ALSEQPINVALIDPROG 121
#define ERR_ALSEQPUNKNOWNMIDI 122
#define ERR_ALSEQPUNMAP 123
#define ERR_ALEVENTNOFREE 124
#define ERR_ALHEAPNOFREE 125
#define ERR_ALHEAPCORRUPT 126
#define ERR_ALHEAPFIRSTBLOCK 127
#define ERR_ALCSEQZEROSTATUS 128
#define ERR_ALCSEQZEROVEL 129
#define ERR_ALCSPVNOTFREE 130
#define ERR_ALSEQOVERRUN 131
#define ERR_OSAISETNEXTBUFFER_ENDADDR 132
#define ERR_ALMODDELAYOVERFLOW 133
#define __log__ 
#define OS_LOG_MAX_ARGS 16
#define OS_LOG_MAGIC 0x20736a73
#define OS_LOG_FLOAT(x) (*(int*) &(x))
#define OS_LOG_VERSION 1
#define FIXED_TO_DEG(fixed) (f32)(fixed * (360.0f / 65536.0f))
#define DEG_TO_FIXED(degrees) (u16)((degrees) * 65536.0f / 360.0f)
#define NISITENMA_ICHIGO_H 
#define NI_ASSETS_MENU_BUFFER_SIZE 0x30000
#define NPTR 0
#define OFFSET_OF(type,member) ((u32) & ((type*) 0)->member)
#define ARRAY_COUNT(arr) (s32)(sizeof(arr) / sizeof(arr[0]))
#define ARRAY_START(arr) &arr[0]
#define ARRAY_END(arr) &arr[ARRAY_COUNT(arr)]
#define SCREEN_WIDTH 320
#define SCREEN_HEIGHT 240
#define FOREST_LOCKED_DOOR 1
#define FOREST_LADY_WHO_BLESSES_INSCRIPTION 4
#define FOREST_LADY_WHO_BLESSES_STATUE 5
#define FOREST_ACTIVATE_LEVER 6
#define FOREST_DEAD_SKELETON 8
#define FOREST_DEAD_BODY 10
#define VILLA_OUTSIDE_CHIMERA_STATUE 6
#define CASTLE_WALL_MAIN_OPEN_GRATING 8
#define CASTLE_WALL_MAIN_GRATING_ALREADY_OPENED 9
#define WATERWAY_DOOR_CLOSED 10
#define CASTLE_CENTER_MAIN_WALL_INFO 2
#define CASTLE_CENTER_MAIN_TAKE_MANDRAGORA 10
#define CASTLE_CENTER_MAIN_OBTAINED_MANDRAGORA 11
#define CASTLE_CENTER_MAIN_MANDRAGORA_INFO 13
#define CASTLE_CENTER_MAIN_SET_NITRO 14
#define CASTLE_CENTER_MAIN_SET_MANDRAGORA 15
#define CASTLE_CENTER_MAIN_ITEM_ALREADY_SET 16
#define CASTLE_CENTER_MAIN_NITRO_SET 17
#define CASTLE_CENTER_MAIN_MANDRAGORA_SET 18
#define CASTLE_CENTER_MAIN_READY_FOR_BLASTING 19
#define CASTLE_CENTER_1F_ACTIVATE_ELEVATOR 1
#define CASTLE_CENTER_1F_ELEVATOR_ACTIVATED 2
#define CASTLE_CENTER_1F_CANT_ACTIVATE_ELEVATOR_YET 3
#define CASTLE_CENTER_1F_ELEVATOR_ALREADY_USED 4
#define CASTLE_CENTER_1F_ELEVATOR_NOT_MOVING 5
#define CASTLE_CENTER_1F_DISPOSAL_WITH_NITRO 7
#define CASTLE_CENTER_1F_DISPOSAL_WITHOUT_NITRO 8
#define CASTLE_CENTER_2F_DISPOSAL_WITH_NITRO 2
#define CASTLE_CENTER_2F_DISPOSAL_WITHOUT_NITRO 3
#define CASTLE_CENTER_3F_WALL_INFO 0
#define CASTLE_CENTER_3F_DISPOSAL_WITH_NITRO 3
#define CASTLE_CENTER_3F_DISPOSAL_WITHOUT_NITRO 4
#define CASTLE_CENTER_3F_NITRO_INFO 5
#define CASTLE_CENTER_3F_TAKE_NITRO 6
#define CASTLE_CENTER_3F_NITRO_WARNING 7
#define CASTLE_CENTER_3F_SET_NITRO 12
#define CASTLE_CENTER_3F_SET_MANDRAGORA 13
#define CASTLE_CENTER_3F_ITEM_ALREADY_SET 14
#define CASTLE_CENTER_3F_NITRO_SET 15
#define CASTLE_CENTER_3F_MANDRAGORA_SET 16
#define CASTLE_CENTER_3F_READY_FOR_BLASTING 17
#define CASTLE_CENTER_4F_LIBRARY_PUZZLE_DESCRIPTION 7
#define CASTLE_CENTER_4F_LIBRARY_PUZZLE_GOLD_PIECE 8
#define CASTLE_CENTER_4F_LIBRARY_PUZZLE_RED_PIECE 9
#define CASTLE_CENTER_4F_LIBRARY_PUZZLE_BLUE_PIECE 10
#define CASTLE_CENTER_4F_LIBRARY_PUZZLE_FAIL 11
#define CASTLE_CENTER_TRY_HAVING_MANDRAGORA_AND_NITRO_SAME_TIME 12
#define GET_UNMAPPED_ADDRESS(file_ID,data_ptr) (u32) sys.Nisitenma_Ichigo_loaded_files_ptr[file_ID] + BITS_MASK((u32) data_ptr, 0xFFFFFF)
#define GET_MAP_MESSAGE_POOL_PTR() (*NisitenmaIchigoFiles_segmentToVirtual)( map_text_segment_address[sys.SaveStruct_gameplay.map], MAP_ASSETS_FILE_ID )
#define GET_MAP_MESSAGE_POOL_PTR_NO_FUNC_PTR() NisitenmaIchigoFiles_segmentToVirtual( map_text_segment_address[sys.SaveStruct_gameplay.map], MAP_ASSETS_FILE_ID )
#define MODEL_INFO_H 
#define COLOR_H 
#define RGBA(r,g,b,a) (((r) << 24) | ((g) << 16) | ((b) << 8) | (a))
#define HIERARCHY_H 
#define MAP_ACTOR_MODEL_H 
#define COLLISION_H 
#define COLL_TYPE_FLOOR 1
#define COLL_TYPE_WALL 2
#define COLL_TYPE_CEILING 4
#define MINI_SCROLL_H 
#define OBJECT_H 
#define FIGURE_H 
#define FIG_SIZE 0xA8
#define FIG_ARRAY_MAX 512
#define FIG_TYPE_STANDALONE 0x0004
#define FIG_TYPE_MAP_PIECE 0x0008
#define FIG_TYPE_HUD_ELEMENT 0x0010
#define FIG_TYPE_DONT_ANIMATE 0x0020
#define FIG_TYPE_HIERARCHY_NODE 0x0040
#define FIG_TYPE_LIGHT 0x0080
#define FIG_TYPE_CAMERA_ORTHO 0x0100
#define FIG_TYPE_CAMERA_PERSPECTIVE 0x0200
#define FIG_TYPE_ALLOW_TRANSPARENCY_CHANGE 0x0400
#define FIG_TYPE_CAMERA_CUTSCENE 0x0800
#define FIG_TYPE_HIERARCHY_FIRST_NODE 0x1000
#define FIG_TYPE_HIERARCHY_ROOT 0x2000
#define FIG_TYPE_SHOW 0x7FFF
#define FIG_TYPE_HIDE 0x8000
#define FIG_TYPE_DATA 0x8000
#define FIG_VARIABLE_TEXTURE_AND_PALETTE 0x40000000
#define FIG_APPLY_VARIABLE_TEXTURE_AND_PALETTE(dlist) (FIG_VARIABLE_TEXTURE_AND_PALETTE | (dlist))
#define FIG_IS_HIDDEN(fig) (fig->type < 0)
#define FIG_HEADER_SIZE sizeof(FigureHeader)
#define GRAPHIC_CONTAINER_H 
#define GFX_MISC_H 
#define NUM_GRAPHIC_BUFFERS 2
#define MEMORY_H 
#define ALIGN8_BITWISE(val) ((((u32) val) + 7) & ~7)
#define ALIGN8_ARITHMETIC(val) ((((u32) (val + 7)) / 8) * 8)
#define HEAP_MULTIPURPOSE_SIZE 0xD0000
#define HEAP_MENU_DATA_SIZE 0x40000
#define HEAP_NUM 8
#define OBJECT_ID_H 
#define OBJECT_ID(kind,id) (((kind) << 8) | (id))
#define OBJECT_ARRAY_MAX 384
#define OBJECT_NUM_MAX 554
#define OBJ_NUM_FIGURES 4
#define OBJ_NUM_ALLOC_DATA 16
#define OBJECT_SIZE sizeof(Object)
#define OBJECT_HEADER_SIZE sizeof(ObjectHeader)
#define OBJECT_FILE_INFO_FLAG_NONE 0x00
#define OBJECT_FILE_INFO_FLAG_LAST 0x40
#define ENTER(self,functions_array) { s16 funcID; funcID = self->header.function_info_ID + 1; self->header.function_info_ID = funcID, self->header.current_function[funcID].timer++; functions_array[self->header.current_function[funcID].function](self); self->header.function_info_ID--; }
#define GO_TO_NEXT_FUNC_NOW(self,functions_array) { ObjectFuncInfo* curFunc; (*object_curLevel_goToNextFuncAndClearTimer)( self->header.current_function, &self->header.function_info_ID ); curFunc = &self->header.current_function[self->header.function_info_ID]; curFunc->timer++, functions_array[curFunc->function](self); }
#define GO_TO_FUNC_NOW(self,functions_array,function_array_ID) { ObjectFuncInfo* curFunc; (*object_curLevel_goToFunc)( self->header.current_function, &self->header.function_info_ID, function_array_ID ); curFunc = &self->header.current_function[self->header.function_info_ID]; curFunc->timer++, functions_array[curFunc->function](self); }
#define CAMERA_H 
#define GAMEPLAY_MENU_MGR_H 
#define MFDS_H 
#define LENS_H 
#define DISTORTION_H 
#define WINDOW_H 
#define STRUCT_78_H 
#define TEXTBOX_ADVANCE_ARROW_H 
#define LIGHT_H 
#define ASCII_TO_CV64(ascii) (ascii - 0x1E)
#define PIXEL_HUD_0 0x68
#define CTRL_SET_COLOR(arg) (0xA200 | (arg & 0xFF))
#define TEXT_COLOR_WHITE 0
#define TEXT_COLOR_RED 1
#define TEXT_COLOR_BEIGE 2
#define TEXT_COLOR_BROWN 3
#define MENU_TEXT_KEY_CONFIG 1
#define MENU_TEXT_SOUND 2
#define MENU_TEXT_DEFAULT 3
#define MENU_TEXT_EXIT 4
#define MENU_TEXT_GAME_START 5
#define MENU_TEXT_DATA_COPY 6
#define MENU_TEXT_DATA_DELETE 7
#define MENU_TEXT_NEW_GAME 8
#define MENU_TEXT_USED_MEMORY 9
#define MENU_TEXT_REINHARDT 10
#define MENU_TEXT_CARRIE 11
#define MENU_TEXT_CORNELL 12
#define MENU_TEXT_COLLER 13
#define MENU_TEXT_TYPE 14
#define MENU_TEXT_A 15
#define MENU_TEXT_B 16
#define MENU_TEXT_C 17
#define MENU_TEXT_STEREO 18
#define MENU_TEXT_MONOAURAL 19
#define MENU_TEXT_NO 20
#define MENU_TEXT_1 21
#define MENU_TEXT_2 22
#define MENU_TEXT_3 23
#define MENU_TEXT_OK_A 24
#define MENU_TEXT_CANCEL_B 25
#define TEXTBOX_OPTION_IDLE 0
#define TEXTBOX_OPTION_YES 1
#define TEXTBOX_OPTION_NO 2
#define HUD_H 
#define HUD_PARAMS_ENTERED_PAUSE_MENU BIT(0)
#define HUD_PARAMS_IN_PAUSE_MENU BIT(1)
#define HUD_PARAMS_SHOW_BOSS_BAR BIT(2)
#define HUD_PARAMS_UPDATE_HUD_GOLD_AND_JEWEL BIT(3)
#define HUD_PARAMS_CLOSE_CLOCK BIT(5)
#define HUD_PARAMS_HIDE_HUD BIT(6)
#define HUD_PARAMS_DESTROY_HUD BIT(7)






typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned long u32;
typedef unsigned long long u64;
typedef signed char s8;
typedef short s16;
typedef long s32;
typedef long long s64;
typedef volatile unsigned char vu8;
typedef volatile unsigned short vu16;
typedef volatile unsigned long vu32;
typedef volatile unsigned long long vu64;
typedef volatile signed char vs8;
typedef volatile short vs16;
typedef volatile long vs32;
typedef volatile long long vs64;
typedef float f32;
typedef double f64;
typedef unsigned int size_t;
typedef struct {
    short ob[3];
    unsigned short flag;
    short tc[2];
    unsigned char cn[4];
} Vtx_t;
typedef struct {
    short ob[3];
    unsigned short flag;
    short tc[2];
    signed char n[3];
    unsigned char a;
} Vtx_tn;
typedef union {
    Vtx_t v;
    Vtx_tn n;
    long long int force_structure_alignment;
} Vtx;
typedef struct {
    void* SourceImagePointer;
    void* TlutPointer;
    short Stride;
    short SubImageWidth;
    short SubImageHeight;
    char SourceImageType;
    char SourceImageBitSize;
    short SourceImageOffsetS;
    short SourceImageOffsetT;
    char dummy[4];
} uSprite_t;
typedef union {
    uSprite_t s;
    long long int force_structure_allignment[3];
} uSprite;
typedef struct {
    unsigned char flag;
    unsigned char v[3];
} Tri;
typedef long Mtx_t[4][4];
typedef union {
    Mtx_t m;
    long long int force_structure_alignment;
} Mtx;
typedef struct {
    short vscale[4];
    short vtrans[4];
} Vp_t;
typedef union {
    Vp_t vp;
    long long int force_structure_alignment;
} Vp;
typedef struct {
    unsigned char col[3];
    char pad1;
    unsigned char colc[3];
    char pad2;
    signed char dir[3];
    char pad3;
} Light_t;
typedef struct {
    unsigned char col[3];
    char pad1;
    unsigned char colc[3];
    char pad2;
} Ambient_t;
typedef struct {
    int x1, y1, x2, y2;
} Hilite_t;
typedef union {
    Light_t l;
    long long int force_structure_alignment[2];
} Light;
typedef union {
    Ambient_t l;
    long long int force_structure_alignment[1];
} Ambient;
typedef struct {
    Ambient a;
    Light l[7];
} Lightsn;
typedef struct {
    Ambient a;
    Light l[1];
} Lights0;
typedef struct {
    Ambient a;
    Light l[1];
} Lights1;
typedef struct {
    Ambient a;
    Light l[2];
} Lights2;
typedef struct {
    Ambient a;
    Light l[3];
} Lights3;
typedef struct {
    Ambient a;
    Light l[4];
} Lights4;
typedef struct {
    Ambient a;
    Light l[5];
} Lights5;
typedef struct {
    Ambient a;
    Light l[6];
} Lights6;
typedef struct {
    Ambient a;
    Light l[7];
} Lights7;
typedef struct {
    Light l[2];
} LookAt;
typedef union {
    Hilite_t h;
    long int force_structure_alignment[4];
} Hilite;
typedef struct {
    int cmd : 8;
    unsigned int par : 8;
    unsigned int len : 16;
    unsigned int addr;
} Gdma;
typedef struct {
    int cmd : 8;
    int pad : 24;
    Tri tri;
} Gtri;
typedef struct {
    int cmd : 8;
    int pad1 : 24;
    int pad2 : 24;
    unsigned char param : 8;
} Gpopmtx;
typedef struct {
    int cmd : 8;
    int pad0 : 8;
    int mw_index : 8;
    int number : 8;
    int pad1 : 8;
    int base : 24;
} Gsegment;
typedef struct {
    int cmd : 8;
    int pad0 : 8;
    int sft : 8;
    int len : 8;
    unsigned int data : 32;
} GsetothermodeL;
typedef struct {
    int cmd : 8;
    int pad0 : 8;
    int sft : 8;
    int len : 8;
    unsigned int data : 32;
} GsetothermodeH;
typedef struct {
    unsigned char cmd;
    unsigned char lodscale;
    unsigned char tile;
    unsigned char on;
    unsigned short s;
    unsigned short t;
} Gtexture;
typedef struct {
    int cmd : 8;
    int pad : 24;
    Tri line;
} Gline3D;
typedef struct {
    int cmd : 8;
    int pad1 : 24;
    short int pad2;
    short int scale;
} Gperspnorm;
typedef struct {
    int cmd : 8;
    unsigned int fmt : 3;
    unsigned int siz : 2;
    unsigned int pad : 7;
    unsigned int wd : 12;
    unsigned int dram;
} Gsetimg;
typedef struct {
    int cmd : 8;
    unsigned int muxs0 : 24;
    unsigned int muxs1 : 32;
} Gsetcombine;
typedef struct {
    int cmd : 8;
    unsigned char pad;
    unsigned char prim_min_level;
    unsigned char prim_level;
    unsigned long color;
} Gsetcolor;
typedef struct {
    int cmd : 8;
    int x0 : 10;
    int x0frac : 2;
    int y0 : 10;
    int y0frac : 2;
    unsigned int pad : 8;
    int x1 : 10;
    int x1frac : 2;
    int y1 : 10;
    int y1frac : 2;
} Gfillrect;
typedef struct {
    int cmd : 8;
    unsigned int fmt : 3;
    unsigned int siz : 2;
    unsigned int pad0 : 1;
    unsigned int line : 9;
    unsigned int tmem : 9;
    unsigned int pad1 : 5;
    unsigned int tile : 3;
    unsigned int palette : 4;
    unsigned int ct : 1;
    unsigned int mt : 1;
    unsigned int maskt : 4;
    unsigned int shiftt : 4;
    unsigned int cs : 1;
    unsigned int ms : 1;
    unsigned int masks : 4;
    unsigned int shifts : 4;
} Gsettile;
typedef struct {
    int cmd : 8;
    unsigned int sl : 12;
    unsigned int tl : 12;
    int pad : 5;
    unsigned int tile : 3;
    unsigned int sh : 12;
    unsigned int th : 12;
} Gloadtile;
typedef Gloadtile Gloadblock;
typedef Gloadtile Gsettilesize;
typedef Gloadtile Gloadtlut;
typedef struct {
    unsigned int cmd : 8;
    unsigned int xl : 12;
    unsigned int yl : 12;
    unsigned int pad1 : 5;
    unsigned int tile : 3;
    unsigned int xh : 12;
    unsigned int yh : 12;
    unsigned int s : 16;
    unsigned int t : 16;
    unsigned int dsdx : 16;
    unsigned int dtdy : 16;
} Gtexrect;
typedef struct {
    unsigned long w0;
    unsigned long w1;
    unsigned long w2;
    unsigned long w3;
} TexRect;
typedef struct {
    unsigned int w0;
    unsigned int w1;
} Gwords;
typedef union {
    Gwords words;
    Gdma dma;
    Gtri tri;
    Gline3D line;
    Gpopmtx popmtx;
    Gsegment segment;
    GsetothermodeH setothermodeH;
    GsetothermodeL setothermodeL;
    Gtexture texture;
    Gperspnorm perspnorm;
    Gsetimg setimg;
    Gsetcombine setcombine;
    Gsetcolor setcolor;
    Gfillrect fillrect;
    Gsettile settile;
    Gloadtile loadtile;
    Gsettilesize settilesize;
    Gloadtlut loadtlut;
    long long int force_structure_alignment;
} Gfx;

typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int gain : 16;
    unsigned int addr;
} Aadpcm;
typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int gain : 16;
    unsigned int addr;
} Apolef;
typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int pad1 : 16;
    unsigned int addr;
} Aenvelope;
typedef struct {
    unsigned int cmd : 8;
    unsigned int pad1 : 8;
    unsigned int dmem : 16;
    unsigned int pad2 : 16;
    unsigned int count : 16;
} Aclearbuff;
typedef struct {
    unsigned int cmd : 8;
    unsigned int pad1 : 8;
    unsigned int pad2 : 16;
    unsigned int inL : 16;
    unsigned int inR : 16;
} Ainterleave;
typedef struct {
    unsigned int cmd : 8;
    unsigned int pad1 : 24;
    unsigned int addr;
} Aloadbuff;
typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int pad1 : 16;
    unsigned int addr;
} Aenvmixer;
typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int gain : 16;
    unsigned int dmemi : 16;
    unsigned int dmemo : 16;
} Amixer;
typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int dmem2 : 16;
    unsigned int addr;
} Apan;
typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int pitch : 16;
    unsigned int addr;
} Aresample;
typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int pad1 : 16;
    unsigned int addr;
} Areverb;
typedef struct {
    unsigned int cmd : 8;
    unsigned int pad1 : 24;
    unsigned int addr;
} Asavebuff;
typedef struct {
    unsigned int cmd : 8;
    unsigned int pad1 : 24;
    unsigned int pad2 : 2;
    unsigned int number : 4;
    unsigned int base : 24;
} Asegment;
typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int dmemin : 16;
    unsigned int dmemout : 16;
    unsigned int count : 16;
} Asetbuff;
typedef struct {
    unsigned int cmd : 8;
    unsigned int flags : 8;
    unsigned int vol : 16;
    unsigned int voltgt : 16;
    unsigned int volrate : 16;
} Asetvol;
typedef struct {
    unsigned int cmd : 8;
    unsigned int pad1 : 8;
    unsigned int dmemin : 16;
    unsigned int dmemout : 16;
    unsigned int count : 16;
} Admemmove;
typedef struct {
    unsigned int cmd : 8;
    unsigned int pad1 : 8;
    unsigned int count : 16;
    unsigned int addr;
} Aloadadpcm;
typedef struct {
    unsigned int cmd : 8;
    unsigned int pad1 : 8;
    unsigned int pad2 : 16;
    unsigned int addr;
} Asetloop;
typedef struct {
    unsigned int w0;
    unsigned int w1;
} Awords;
typedef union {
    Awords words;
    Aadpcm adpcm;
    Apolef polef;
    Aclearbuff clearbuff;
    Aenvelope envelope;
    Ainterleave interleave;
    Aloadbuff loadbuff;
    Aenvmixer envmixer;
    Aresample resample;
    Areverb reverb;
    Asavebuff savebuff;
    Asegment segment;
    Asetbuff setbuff;
    Asetvol setvol;
    Admemmove dmemmove;
    Aloadadpcm loadadpcm;
    Amixer mixer;
    Asetloop setloop;
    long long int force_union_align;
} Acmd;
typedef short ADPCM_STATE[16];
typedef short POLEF_STATE[4];
typedef short RESAMPLE_STATE[16];
typedef short ENVMIX_STATE[40];
typedef struct {
    u32 type;
    u32 flags;
    u64* ucode_boot;
    u32 ucode_boot_size;
    u64* ucode;
    u32 ucode_size;
    u64* ucode_data;
    u32 ucode_data_size;
    u64* dram_stack;
    u32 dram_stack_size;
    u64* output_buff;
    u64* output_buff_size;
    u64* data_ptr;
    u32 data_size;
    u64* yield_data_ptr;
    u32 yield_data_size;
} OSTask_t;
typedef union {
    OSTask_t t;
    long long int force_structure_alignment;
} OSTask;
typedef u32 OSYieldResult;
extern void osSpTaskLoad(OSTask* tp);
extern void osSpTaskStartGo(OSTask* tp);
extern void osSpTaskYield(void);
extern OSYieldResult osSpTaskYielded(OSTask* tp);
typedef struct {
    unsigned char* base;
    int fmt, siz;
    int xsize, ysize;
    int lsize;
    int addr;
    int w, h;
    int s, t;
} Image;
typedef struct {
    float col[3];
    float pos[3];
    float a1, a2;
} PositionalLight;
extern int guLoadTextureBlockMipMap(Gfx** glist, unsigned char* tbuf, Image* im,
                                    unsigned char startTile, unsigned char pal,
                                    unsigned char cms, unsigned char cmt,
                                    unsigned char masks, unsigned char maskt,
                                    unsigned char shifts, unsigned char shiftt,
                                    unsigned char cfs, unsigned char cft);
extern int guGetDPLoadTextureTileSz(int ult, int lrt);
extern void guDPLoadTextureTile(Gfx* glistp, void* timg, int texl_fmt,
                                int texl_size, int img_width, int img_height,
                                int uls, int ult, int lrs, int lrt, int palette,
                                int cms, int cmt, int masks, int maskt,
                                int shifts, int shiftt);
extern void guMtxIdent(Mtx* m);
extern void guMtxIdentF(float mf[4][4]);
extern void guOrtho(Mtx* m, float l, float r, float b, float t, float n,
                    float f, float scale);
extern void guOrthoF(float mf[4][4], float l, float r, float b, float t,
                     float n, float f, float scale);
extern void guFrustum(Mtx* m, float l, float r, float b, float t, float n,
                      float f, float scale);
extern void guFrustumF(float mf[4][4], float l, float r, float b, float t,
                       float n, float f, float scale);
extern void guPerspective(Mtx* m, u16* perspNorm, float fovy, float aspect,
                          float near, float far, float scale);
extern void guPerspectiveF(float mf[4][4], u16* perspNorm, float fovy,
                           float aspect, float near, float far, float scale);
extern void guLookAt(Mtx* m, float xEye, float yEye, float zEye, float xAt,
                     float yAt, float zAt, float xUp, float yUp, float zUp);
extern void guLookAtF(float mf[4][4], float xEye, float yEye, float zEye,
                      float xAt, float yAt, float zAt, float xUp, float yUp,
                      float zUp);
extern void guLookAtReflect(Mtx* m, LookAt* l, float xEye, float yEye,
                            float zEye, float xAt, float yAt, float zAt,
                            float xUp, float yUp, float zUp);
extern void guLookAtReflectF(float mf[4][4], LookAt* l, float xEye, float yEye,
                             float zEye, float xAt, float yAt, float zAt,
                             float xUp, float yUp, float zUp);
extern void guLookAtHilite(Mtx* m, LookAt* l, Hilite* h, float xEye, float yEye,
                           float zEye, float xAt, float yAt, float zAt,
                           float xUp, float yUp, float zUp, float xl1,
                           float yl1, float zl1, float xl2, float yl2,
                           float zl2, int twidth, int theight);
extern void guLookAtHiliteF(float mf[4][4], LookAt* l, Hilite* h, float xEye,
                            float yEye, float zEye, float xAt, float yAt,
                            float zAt, float xUp, float yUp, float zUp,
                            float xl1, float yl1, float zl1, float xl2,
                            float yl2, float zl2, int twidth, int theight);
extern void guLookAtStereo(Mtx* m, float xEye, float yEye, float zEye,
                           float xAt, float yAt, float zAt, float xUp,
                           float yUp, float zUp, float eyedist);
extern void guLookAtStereoF(float mf[4][4], float xEye, float yEye, float zEye,
                            float xAt, float yAt, float zAt, float xUp,
                            float yUp, float zUp, float eyedist);
extern void guRotate(Mtx* m, float a, float x, float y, float z);
extern void guRotateF(float mf[4][4], float a, float x, float y, float z);
extern void guRotateRPY(Mtx* m, float r, float p, float y);
extern void guRotateRPYF(float mf[4][4], float r, float p, float h);
extern void guAlign(Mtx* m, float a, float x, float y, float z);
extern void guAlignF(float mf[4][4], float a, float x, float y, float z);
extern void guScale(Mtx* m, float x, float y, float z);
extern void guScaleF(float mf[4][4], float x, float y, float z);
extern void guTranslate(Mtx* m, float x, float y, float z);
extern void guTranslateF(float mf[4][4], float x, float y, float z);
extern void guPosition(Mtx* m, float r, float p, float h, float s, float x,
                       float y, float z);
extern void guPositionF(float mf[4][4], float r, float p, float h, float s,
                        float x, float y, float z);
extern void guMtxF2L(float mf[4][4], Mtx* m);
extern void guMtxL2F(float mf[4][4], Mtx* m);
extern void guMtxCatF(float m[4][4], float n[4][4], float r[4][4]);
extern void guMtxCatL(Mtx* m, Mtx* n, Mtx* res);
extern void guMtxXFMF(float mf[4][4], float x, float y, float z, float* ox,
                      float* oy, float* oz);
extern void guMtxXFML(Mtx* m, float x, float y, float z, float* ox, float* oy,
                      float* oz);
extern void guNormalize(float* x, float* y, float* z);
void guPosLight(PositionalLight* pl, Light* l, float xOb, float yOb, float zOb);
void guPosLightHilite(PositionalLight* pl1, PositionalLight* pl2, Light* l1,
                      Light* l2, LookAt* l, Hilite* h, float xEye, float yEye,
                      float zEye, float xOb, float yOb, float zOb, float xUp,
                      float yUp, float zUp, int twidth, int theight);
extern int guRandom(void);
extern float sinf(float angle);
extern float cosf(float angle);
extern signed short sins(unsigned short angle);
extern signed short coss(unsigned short angle);
extern float sqrtf(float value);
extern void guParseRdpDL(u64* rdp_dl, u64 nbytes, u8 flags);
extern void guParseString(char* StringPointer, u64 nbytes);
extern void guBlinkRdpDL(u64* rdp_dl_in, u64 nbytes_in, u64* rdp_dl_out,
                         u64* nbytes_out, u32 x, u32 y, u32 radius, u8 red,
                         u8 green, u8 blue, u8 flags);
extern void guParseGbiDL(u64* gbi_dl, u32 nbytes, u8 flags);
extern void guDumpGbiDL(OSTask* tp, u8 flags);
typedef struct {
    int dataSize;
    int dlType;
    int flags;
    u32 paddr;
} guDLPrintCB;
void guSprite2DInit(uSprite* SpritePointer, void* SourceImagePointer,
                    void* TlutPointer, int Stride, int SubImageWidth,
                    int SubImageHeight, int SourceImageType,
                    int SourceImageBitSize, int SourceImageOffsetS,
                    int SourceImageOffsetT);
typedef s32 ALMicroTime;
typedef u8 ALPan;
typedef struct ALLink_s {
    struct ALLink_s* next;
    struct ALLink_s* prev;
} ALLink;
void alUnlink(ALLink* element);
void alLink(ALLink* element, ALLink* after);
typedef s32 (*ALDMAproc)(s32 addr, s32 len, void* state);
typedef ALDMAproc (*ALDMANew)(void* state);
void alCopy(void* src, void* dest, s32 len);
typedef struct {
    u8* base;
    u8* cur;
    s32 len;
    s32 count;
} ALHeap;
void alHeapInit(ALHeap* hp, u8* base, s32 len);
void* alHeapDBAlloc(u8* file, s32 line, ALHeap* hp, s32 num, s32 size);
s32 alHeapCheck(ALHeap* hp);
typedef u8 ALFxId;
typedef void* ALFxRef;
enum { AL_ADPCM_WAVE = 0, AL_RAW16_WAVE };
typedef struct {
    s32 order;
    s32 npredictors;
    s16 book[1];
} ALADPCMBook;
typedef struct {
    u32 start;
    u32 end;
    u32 count;
    ADPCM_STATE state;
} ALADPCMloop;
typedef struct {
    u32 start;
    u32 end;
    u32 count;
} ALRawLoop;
typedef struct {
    ALMicroTime attackTime;
    ALMicroTime decayTime;
    ALMicroTime releaseTime;
    u8 attackVolume;
    u8 decayVolume;
} ALEnvelope;
typedef struct {
    u8 velocityMin;
    u8 velocityMax;
    u8 keyMin;
    u8 keyMax;
    u8 keyBase;
    s8 detune;
} ALKeyMap;
typedef struct {
    ALADPCMloop* loop;
    ALADPCMBook* book;
} ALADPCMWaveInfo;
typedef struct {
    ALRawLoop* loop;
} ALRAWWaveInfo;
typedef struct ALWaveTable_s {
    u8* base;
    s32 len;
    u8 type;
    u8 flags;
    union {
        ALADPCMWaveInfo adpcmWave;
        ALRAWWaveInfo rawWave;
    } waveInfo;
} ALWaveTable;
typedef struct ALSound_s {
    ALEnvelope* envelope;
    ALKeyMap* keyMap;
    ALWaveTable* wavetable;
    ALPan samplePan;
    u8 sampleVolume;
    u8 flags;
} ALSound;
typedef struct {
    u8 volume;
    ALPan pan;
    u8 priority;
    u8 flags;
    u8 tremType;
    u8 tremRate;
    u8 tremDepth;
    u8 tremDelay;
    u8 vibType;
    u8 vibRate;
    u8 vibDepth;
    u8 vibDelay;
    s16 bendRange;
    s16 soundCount;
    ALSound* soundArray[1];
} ALInstrument;
typedef struct ALBank_s {
    s16 instCount;
    u8 flags;
    u8 pad;
    s32 sampleRate;
    ALInstrument* percussion;
    ALInstrument* instArray[1];
} ALBank;
typedef struct {
    s16 revision;
    s16 bankCount;
    ALBank* bankArray[1];
} ALBankFile;
void alBnkfNew(ALBankFile* f, u8* table);
typedef struct {
    u8* offset;
    s32 len;
} ALSeqData;
typedef struct {
    s16 revision;
    s16 seqCount;
    ALSeqData seqArray[1];
} ALSeqFile;
void alSeqFileNew(ALSeqFile* f, u8* base);
typedef ALMicroTime (*ALVoiceHandler)(void*);
typedef struct {
    s32 maxVVoices;
    s32 maxPVoices;
    s32 maxUpdates;
    s32 maxFXbusses;
    void* dmaproc;
    ALHeap* heap;
    s32 outputRate;
    ALFxId fxType;
    s32* params;
} ALSynConfig;
typedef struct ALPlayer_s {
    struct ALPlayer_s* next;
    void* clientData;
    ALVoiceHandler handler;
    ALMicroTime callTime;
    s32 samplesLeft;
} ALPlayer;
typedef struct ALVoice_s {
    ALLink node;
    struct PVoice_s* pvoice;
    ALWaveTable* table;
    void* clientPrivate;
    s16 state;
    s16 priority;
    s16 fxBus;
    s16 unityPitch;
} ALVoice;
typedef struct ALVoiceConfig_s {
    s16 priority;
    s16 fxBus;
    u8 unityPitch;
} ALVoiceConfig;
typedef struct {
    ALPlayer* head;
    ALLink pFreeList;
    ALLink pAllocList;
    ALLink pLameList;
    s32 paramSamples;
    s32 curSamples;
    ALDMANew dma;
    ALHeap* heap;
    struct ALParam_s* paramList;
    struct ALMainBus_s* mainBus;
    struct ALAuxBus_s* auxBus;
    struct ALFilter_s* outputFilter;
    s32 numPVoices;
    s32 maxAuxBusses;
    s32 outputRate;
    s32 maxOutSamples;
} ALSynth;
void alSynNew(ALSynth* s, ALSynConfig* config);
void alSynDelete(ALSynth* s);
void alSynAddPlayer(ALSynth* s, ALPlayer* client);
void alSynRemovePlayer(ALSynth* s, ALPlayer* client);
s32 alSynAllocVoice(ALSynth* s, ALVoice* v, ALVoiceConfig* vc);
void alSynFreeVoice(ALSynth* s, ALVoice* voice);
void alSynStartVoice(ALSynth* s, ALVoice* voice, ALWaveTable* w);
void alSynStartVoiceParams(ALSynth* s, ALVoice* voice, ALWaveTable* w,
                           f32 pitch, s16 vol, ALPan pan, u8 fxmix,
                           ALMicroTime t);
void alSynStopVoice(ALSynth* s, ALVoice* voice);
void alSynSetVol(ALSynth* s, ALVoice* v, s16 vol, ALMicroTime delta);
void alSynSetPitch(ALSynth* s, ALVoice* voice, f32 ratio);
void alSynSetPan(ALSynth* s, ALVoice* voice, ALPan pan);
void alSynSetFXMix(ALSynth* s, ALVoice* voice, u8 fxmix);
void alSynSetPriority(ALSynth* s, ALVoice* voice, s16 priority);
s16 alSynGetPriority(ALSynth* s, ALVoice* voice);
ALFxRef* alSynAllocFX(ALSynth* s, s16 bus, ALSynConfig* c, ALHeap* hp);
ALFxRef alSynGetFXRef(ALSynth* s, s16 bus, s16 index);
void alSynFreeFX(ALSynth* s, ALFxRef* fx);
void alSynSetFXParam(ALSynth* s, ALFxRef fx, s16 paramID, void* param);
typedef struct {
    ALSynth drvr;
} ALGlobals;
extern ALGlobals* alGlobals;
void alInit(ALGlobals* glob, ALSynConfig* c);
void alClose(ALGlobals* glob);
Acmd* alAudioFrame(Acmd* cmdList, s32* cmdLen, s16* outBuf, s32 outLen);
enum ALMsg {
    AL_SEQ_REF_EVT,
    AL_SEQ_MIDI_EVT,
    AL_SEQP_MIDI_EVT,
    AL_TEMPO_EVT,
    AL_SEQ_END_EVT,
    AL_NOTE_END_EVT,
    AL_SEQP_ENV_EVT,
    AL_SEQP_META_EVT,
    AL_SEQP_PROG_EVT,
    AL_SEQP_API_EVT,
    AL_SEQP_VOL_EVT,
    AL_SEQP_LOOP_EVT,
    AL_SEQP_PRIORITY_EVT,
    AL_SEQP_SEQ_EVT,
    AL_SEQP_BANK_EVT,
    AL_SEQP_PLAY_EVT,
    AL_SEQP_STOP_EVT,
    AL_SEQP_STOPPING_EVT,
    AL_TRACK_END,
    AL_CSP_LOOPSTART,
    AL_CSP_LOOPEND,
    AL_CSP_NOTEOFF_EVT,
    AL_TREM_OSC_EVT,
    AL_VIB_OSC_EVT
};
enum AL_MIDIstatus {
    AL_MIDI_ChannelMask = 0x0F,
    AL_MIDI_StatusMask = 0xF0,
    AL_MIDI_ChannelVoice = 0x80,
    AL_MIDI_NoteOff = 0x80,
    AL_MIDI_NoteOn = 0x90,
    AL_MIDI_PolyKeyPressure = 0xA0,
    AL_MIDI_ControlChange = 0xB0,
    AL_MIDI_ChannelModeSelect = 0xB0,
    AL_MIDI_ProgramChange = 0xC0,
    AL_MIDI_ChannelPressure = 0xD0,
    AL_MIDI_PitchBendChange = 0xE0,
    AL_MIDI_SysEx = 0xF0,
    AL_MIDI_SystemCommon = 0xF1,
    AL_MIDI_TimeCodeQuarterFrame = 0xF1,
    AL_MIDI_SongPositionPointer = 0xF2,
    AL_MIDI_SongSelect = 0xF3,
    AL_MIDI_Undefined1 = 0xF4,
    AL_MIDI_Undefined2 = 0xF5,
    AL_MIDI_TuneRequest = 0xF6,
    AL_MIDI_EOX = 0xF7,
    AL_MIDI_SystemRealTime = 0xF8,
    AL_MIDI_TimingClock = 0xF8,
    AL_MIDI_Undefined3 = 0xF9,
    AL_MIDI_Start = 0xFA,
    AL_MIDI_Continue = 0xFB,
    AL_MIDI_Stop = 0xFC,
    AL_MIDI_Undefined4 = 0xFD,
    AL_MIDI_ActiveSensing = 0xFE,
    AL_MIDI_SystemReset = 0xFF,
    AL_MIDI_Meta = 0xFF
};
enum AL_MIDIctrl {
    AL_MIDI_VOLUME_CTRL = 0x07,
    AL_MIDI_PAN_CTRL = 0x0A,
    AL_MIDI_PRIORITY_CTRL =
        0x10,
    AL_MIDI_FX_CTRL_0 = 0x14,
    AL_MIDI_FX_CTRL_1 = 0x15,
    AL_MIDI_FX_CTRL_2 = 0x16,
    AL_MIDI_FX_CTRL_3 = 0x17,
    AL_MIDI_FX_CTRL_4 = 0x18,
    AL_MIDI_FX_CTRL_5 = 0x19,
    AL_MIDI_FX_CTRL_6 = 0x1A,
    AL_MIDI_FX_CTRL_7 = 0x1B,
    AL_MIDI_FX_CTRL_8 = 0x1C,
    AL_MIDI_FX_CTRL_9 = 0x1D,
    AL_MIDI_SUSTAIN_CTRL = 0x40,
    AL_MIDI_FX1_CTRL = 0x5B,
    AL_MIDI_FX3_CTRL = 0x5D
};
enum AL_MIDImeta { AL_MIDI_META_TEMPO = 0x51, AL_MIDI_META_EOT = 0x2f };
typedef struct {
    u8* curPtr;
    s32 lastTicks;
    s32 curTicks;
    s16 lastStatus;
} ALSeqMarker;
typedef struct {
    s32 ticks;
    u8 status;
    u8 byte1;
    u8 byte2;
    u32 duration;
} ALMIDIEvent;
typedef struct {
    s32 ticks;
    u8 status;
    u8 type;
    u8 len;
    u8 byte1;
    u8 byte2;
    u8 byte3;
} ALTempoEvent;
typedef struct {
    s32 ticks;
    u8 status;
    u8 type;
    u8 len;
} ALEndEvent;
typedef struct {
    struct ALVoice_s* voice;
} ALNoteEvent;
typedef struct {
    struct ALVoice_s* voice;
    ALMicroTime delta;
    u8 vol;
} ALVolumeEvent;
typedef struct {
    s16 vol;
} ALSeqpVolEvent;
typedef struct {
    ALSeqMarker* start;
    ALSeqMarker* end;
    s32 count;
} ALSeqpLoopEvent;
typedef struct {
    u8 chan;
    u8 priority;
} ALSeqpPriorityEvent;
typedef struct {
    void* seq;
} ALSeqpSeqEvent;
typedef struct {
    ALBank* bank;
} ALSeqpBankEvent;
typedef struct {
    struct ALVoiceState_s* vs;
    void* oscState;
    u8 chan;
} ALOscEvent;
typedef struct {
    s16 type;
    union {
        ALMIDIEvent midi;
        ALTempoEvent tempo;
        ALEndEvent end;
        ALNoteEvent note;
        ALVolumeEvent vol;
        ALSeqpLoopEvent loop;
        ALSeqpVolEvent spvol;
        ALSeqpPriorityEvent sppriority;
        ALSeqpSeqEvent spseq;
        ALSeqpBankEvent spbank;
        ALOscEvent osc;
    } msg;
} ALEvent;
typedef struct {
    ALLink node;
    ALMicroTime delta;
    ALEvent evt;
} ALEventListItem;
typedef struct {
    ALLink freeList;
    ALLink allocList;
    s32 eventCount;
} ALEventQueue;
void alEvtqNew(ALEventQueue* evtq, ALEventListItem* items, s32 itemCount);
ALMicroTime alEvtqNextEvent(ALEventQueue* evtq, ALEvent* evt);
void alEvtqPostEvent(ALEventQueue* evtq, ALEvent* evt, ALMicroTime delta);
void alEvtqFlush(ALEventQueue* evtq);
void alEvtqFlushType(ALEventQueue* evtq, s16 type);
typedef struct ALVoiceState_s {
    struct ALVoiceState_s* next;
    ALVoice voice;
    ALSound* sound;
    ALMicroTime envEndTime;
    f32 pitch;
    f32 vibrato;
    u8 envGain;
    u8 channel;
    u8 key;
    u8 velocity;
    u8 envPhase;
    u8 phase;
    u8 tremelo;
    u8 flags;
} ALVoiceState;
typedef struct {
    ALInstrument* instrument;
    s16 bendRange;
    ALFxId fxId;
    ALPan pan;
    u8 priority;
    u8 vol;
    u8 fxmix;
    u8 sustain;
    f32 pitchBend;
} ALChanState;
typedef struct ALSeq_s {
    u8* base;
    u8* trackStart;
    u8* curPtr;
    s32 lastTicks;
    s32 len;
    f32 qnpt;
    s16 division;
    s16 lastStatus;
} ALSeq;
typedef struct {
    u32 trackOffset[16];
    u32 division;
} ALCMidiHdr;
typedef struct ALCSeq_s {
    ALCMidiHdr* base;
    u32 validTracks;
    f32 qnpt;
    u32 lastTicks;
    u32 lastDeltaTicks;
    u32 deltaFlag;
    u8* curLoc[16];
    u8* curBUPtr[16];
    u8 curBULen[16];
    u8 lastStatus[16];
    u32 evtDeltaTicks[16];
} ALCSeq;
typedef struct {
    u32 validTracks;
    s32 lastTicks;
    u32 lastDeltaTicks;
    u8* curLoc[16];
    u8* curBUPtr[16];
    u8 curBULen[16];
    u8 lastStatus[16];
    u32 evtDeltaTicks[16];
} ALCSeqMarker;
typedef struct {
    s32 maxVoices;
    s32 maxEvents;
    u8 maxChannels;
    u8 debugFlags;
    ALHeap* heap;
    void* initOsc;
    void* updateOsc;
    void* stopOsc;
} ALSeqpConfig;
typedef ALMicroTime (*ALOscInit)(void** oscState, f32* initVal, u8 oscType,
                                 u8 oscRate, u8 oscDepth, u8 oscDelay);
typedef ALMicroTime (*ALOscUpdate)(void* oscState, f32* updateVal);
typedef void (*ALOscStop)(void* oscState);
typedef struct {
    ALPlayer node;
    ALSynth* drvr;
    ALSeq* target;
    ALMicroTime curTime;
    ALBank* bank;
    s32 uspt;
    s32 nextDelta;
    s32 state;
    u16 chanMask;
    s16 vol;
    u8 maxChannels;
    u8 debugFlags;
    ALEvent nextEvent;
    ALEventQueue evtq;
    ALMicroTime frameTime;
    ALChanState* chanState;
    ALVoiceState* vAllocHead;
    ALVoiceState* vAllocTail;
    ALVoiceState* vFreeList;
    ALOscInit initOsc;
    ALOscUpdate updateOsc;
    ALOscStop stopOsc;
    ALSeqMarker* loopStart;
    ALSeqMarker* loopEnd;
    s32 loopCount;
} ALSeqPlayer;
typedef struct {
    ALPlayer node;
    ALSynth* drvr;
    ALCSeq* target;
    ALMicroTime curTime;
    ALBank* bank;
    s32 uspt;
    s32 nextDelta;
    s32 state;
    u16 chanMask;
    s16 vol;
    u8 maxChannels;
    u8 debugFlags;
    ALEvent nextEvent;
    ALEventQueue evtq;
    ALMicroTime frameTime;
    ALChanState* chanState;
    ALVoiceState* vAllocHead;
    ALVoiceState* vAllocTail;
    ALVoiceState* vFreeList;
    ALOscInit initOsc;
    ALOscUpdate updateOsc;
    ALOscStop stopOsc;
} ALCSPlayer;
void alSeqNew(ALSeq* seq, u8* ptr, s32 len);
void alSeqNextEvent(ALSeq* seq, ALEvent* event);
s32 alSeqGetTicks(ALSeq* seq);
f32 alSeqTicksToSec(ALSeq* seq, s32 ticks, u32 tempo);
u32 alSeqSecToTicks(ALSeq* seq, f32 sec, u32 tempo);
void alSeqNewMarker(ALSeq* seq, ALSeqMarker* m, u32 ticks);
void alSeqSetLoc(ALSeq* seq, ALSeqMarker* marker);
void alSeqGetLoc(ALSeq* seq, ALSeqMarker* marker);
void alCSeqNew(ALCSeq* seq, u8* ptr);
void alCSeqNextEvent(ALCSeq* seq, ALEvent* evt);
s32 alCSeqGetTicks(ALCSeq* seq);
f32 alCSeqTicksToSec(ALCSeq* seq, s32 ticks, u32 tempo);
u32 alCSeqSecToTicks(ALCSeq* seq, f32 sec, u32 tempo);
void alCSeqNewMarker(ALCSeq* seq, ALCSeqMarker* m, u32 ticks);
void alCSeqSetLoc(ALCSeq* seq, ALCSeqMarker* marker);
void alCSeqGetLoc(ALCSeq* seq, ALCSeqMarker* marker);
f32 alCents2Ratio(s32 cents);
void alSeqpNew(ALSeqPlayer* seqp, ALSeqpConfig* config);
void alSeqpDelete(ALSeqPlayer* seqp);
void alSeqpSetSeq(ALSeqPlayer* seqp, ALSeq* seq);
ALSeq* alSeqpGetSeq(ALSeqPlayer* seqp);
void alSeqpPlay(ALSeqPlayer* seqp);
void alSeqpStop(ALSeqPlayer* seqp);
s32 alSeqpGetState(ALSeqPlayer* seqp);
void alSeqpSetBank(ALSeqPlayer* seqp, ALBank* b);
void alSeqpSetTempo(ALSeqPlayer* seqp, s32 tempo);
s32 alSeqpGetTempo(ALSeqPlayer* seqp);
s16 alSeqpGetVol(ALSeqPlayer* seqp);
void alSeqpSetVol(ALSeqPlayer* seqp, s16 vol);
void alSeqpLoop(ALSeqPlayer* seqp, ALSeqMarker* start, ALSeqMarker* end,
                s32 count);
void alSeqpSetChlProgram(ALSeqPlayer* seqp, u8 chan, u8 prog);
s32 alSeqpGetChlProgram(ALSeqPlayer* seqp, u8 chan);
void alSeqpSetChlFXMix(ALSeqPlayer* seqp, u8 chan, u8 fxmix);
u8 alSeqpGetChlFXMix(ALSeqPlayer* seqp, u8 chan);
void alSeqpSetChlVol(ALSeqPlayer* seqp, u8 chan, u8 vol);
u8 alSeqpGetChlVol(ALSeqPlayer* seqp, u8 chan);
void alSeqpSetChlPan(ALSeqPlayer* seqp, u8 chan, ALPan pan);
ALPan alSeqpGetChlPan(ALSeqPlayer* seqp, u8 chan);
void alSeqpSetChlPriority(ALSeqPlayer* seqp, u8 chan, u8 priority);
u8 alSeqpGetChlPriority(ALSeqPlayer* seqp, u8 chan);
void alSeqpSendMidi(ALSeqPlayer* seqp, s32 ticks, u8 status, u8 byte1,
                    u8 byte2);
void alCSPNew(ALCSPlayer* seqp, ALSeqpConfig* config);
void alCSPDelete(ALCSPlayer* seqp);
void alCSPSetSeq(ALCSPlayer* seqp, ALCSeq* seq);
ALCSeq* alCSPGetSeq(ALCSPlayer* seqp);
void alCSPPlay(ALCSPlayer* seqp);
void alCSPStop(ALCSPlayer* seqp);
s32 alCSPGetState(ALCSPlayer* seqp);
void alCSPSetBank(ALCSPlayer* seqp, ALBank* b);
void alCSPSetTempo(ALCSPlayer* seqp, s32 tempo);
s32 alCSPGetTempo(ALCSPlayer* seqp);
s16 alCSPGetVol(ALCSPlayer* seqp);
void alCSPSetVol(ALCSPlayer* seqp, s16 vol);
void alCSPSetChlProgram(ALCSPlayer* seqp, u8 chan, u8 prog);
s32 alCSPGetChlProgram(ALCSPlayer* seqp, u8 chan);
void alCSPSetChlFXMix(ALCSPlayer* seqp, u8 chan, u8 fxmix);
u8 alCSPGetChlFXMix(ALCSPlayer* seqp, u8 chan);
void alCSPSetChlPan(ALCSPlayer* seqp, u8 chan, ALPan pan);
ALPan alCSPGetChlPan(ALCSPlayer* seqp, u8 chan);
void alCSPSetChlVol(ALCSPlayer* seqp, u8 chan, u8 vol);
u8 alCSPGetChlVol(ALCSPlayer* seqp, u8 chan);
void alCSPSetChlPriority(ALCSPlayer* seqp, u8 chan, u8 priority);
u8 alCSPGetChlPriority(ALCSPlayer* seqp, u8 chan);
void alCSPSendMidi(ALCSPlayer* seqp, s32 ticks, u8 status, u8 byte1, u8 byte2);
typedef struct {
    s32 maxSounds;
    s32 maxEvents;
    ALHeap* heap;
} ALSndpConfig;
typedef struct {
    ALPlayer node;
    ALEventQueue evtq;
    ALEvent nextEvent;
    ALSynth* drvr;
    s32 target;
    void* sndState;
    s32 maxSounds;
    ALMicroTime frameTime;
    ALMicroTime nextDelta;
    ALMicroTime curTime;
} ALSndPlayer;
typedef s16 ALSndId;
void alSndpNew(ALSndPlayer* sndp, ALSndpConfig* c);
void alSndpDelete(ALSndPlayer* sndp);
ALSndId alSndpAllocate(ALSndPlayer* sndp, ALSound* sound);
void alSndpDeallocate(ALSndPlayer* sndp, ALSndId id);
void alSndpSetSound(ALSndPlayer* sndp, ALSndId id);
ALSndId alSndpGetSound(ALSndPlayer* sndp);
void alSndpPlay(ALSndPlayer* sndp);
void alSndpPlayAt(ALSndPlayer* sndp, ALMicroTime delta);
void alSndpStop(ALSndPlayer* sndp);
void alSndpSetVol(ALSndPlayer* sndp, s16 vol);
void alSndpSetPitch(ALSndPlayer* sndp, f32 pitch);
void alSndpSetPan(ALSndPlayer* sndp, ALPan pan);
void alSndpSetPriority(ALSndPlayer* sndp, ALSndId id, u8 priority);
void alSndpSetFXMix(ALSndPlayer* sndp, u8 mix);
s32 alSndpGetState(ALSndPlayer* sndp);
void alParseAbiCL(Acmd* cmdList, u32 nbytes);

typedef s32 OSPri;
typedef s32 OSId;
typedef union {
    struct {
        f32 f_odd;
        f32 f_even;
    } f;
    f64 d;
} __OSfp;
typedef struct {
    u64 at, v0, v1, a0, a1, a2, a3;
    u64 t0, t1, t2, t3, t4, t5, t6, t7;
    u64 s0, s1, s2, s3, s4, s5, s6, s7;
    u64 t8, t9;
    u64 gp, sp, s8, ra;
    u64 lo, hi;
    u32 sr, pc, cause, badvaddr, rcp;
    u32 fpcsr;
    __OSfp fp0, fp2, fp4, fp6, fp8, fp10, fp12, fp14;
    __OSfp fp16, fp18, fp20, fp22, fp24, fp26, fp28, fp30;
} __OSThreadContext;
typedef struct {
    u32 flag;
    u32 count;
    u64 time;
} __OSThreadprofile_s;
typedef struct OSThread_s {
    struct OSThread_s* next;
    OSPri priority;
    struct OSThread_s** queue;
    struct OSThread_s* tlnext;
    u16 state;
    u16 flags;
    OSId id;
    int fp;
    __OSThreadprofile_s* thprof;
    __OSThreadContext context;
} OSThread;
extern void osCreateThread(OSThread*, OSId, void (*)(void*), void*, void*,
                           OSPri);
extern void osDestroyThread(OSThread*);
extern void osYieldThread(void);
extern void osStartThread(OSThread*);
extern void osStopThread(OSThread*);
extern OSId osGetThreadId(OSThread*);
extern void osSetThreadPri(OSThread*, OSPri);
extern OSPri osGetThreadPri(OSThread*);
typedef u32 OSEvent;
typedef void* OSMesg;
typedef struct OSMesgQueue_s {
    OSThread* mtqueue;
    OSThread*
        fullqueue;
    s32 validCount;
    s32 first;
    s32 msgCount;
    OSMesg* msg;
} OSMesgQueue;
extern void osCreateMesgQueue(OSMesgQueue*, OSMesg*, s32);
extern s32 osSendMesg(OSMesgQueue*, OSMesg, s32);
extern s32 osJamMesg(OSMesgQueue*, OSMesg, s32);
extern s32 osRecvMesg(OSMesgQueue*, OSMesg*, s32);
extern void osSetEventMesg(OSEvent, OSMesgQueue*, OSMesg);
typedef u64 OSTime;
typedef struct OSTimer_s {
    struct OSTimer_s* next;
    struct OSTimer_s* prev;
    OSTime interval;
    OSTime value;
    OSMesgQueue* mq;
    OSMesg msg;
} OSTimer;
extern OSTime osGetTime(void);
extern void osSetTime(OSTime);
extern int osSetTimer(OSTimer*, OSTime, OSTime, OSMesgQueue*, OSMesg);
extern int osStopTimer(OSTimer*);
extern u32 osAiGetStatus(void);
extern u32 osAiGetLength(void);
extern s32 osAiSetFrequency(u32);
extern s32 osAiSetNextBuffer(void*, u32);
extern void osInvalDCache(void*, s32);
extern void osInvalICache(void*, s32);
extern void osWritebackDCache(void*, s32);
extern void osWritebackDCacheAll(void);
typedef struct {
    u16 type;
    u8 status;
    u8 errno;
} OSContStatus;
typedef struct {
    u16 button;
    s8 stick_x;
    s8 stick_y;
    u8 errno;
} OSContPad;
typedef struct {
    void* address;
    u8 databuffer[32];
    u8 addressCrc;
    u8 dataCrc;
    u8 errno;
} OSContRamIo;
extern s32 osContInit(OSMesgQueue*, u8*, OSContStatus*);
extern s32 osContReset(OSMesgQueue*, OSContStatus*);
extern s32 osContStartQuery(OSMesgQueue*);
extern s32 osContStartReadData(OSMesgQueue*);
extern s32 osContSetCh(u8);
extern void osContGetQuery(OSContStatus*);
extern void osContGetReadData(OSContPad*);
extern u32 osVirtualToPhysical(void*);
extern void* osPhysicalToVirtual(u32);
typedef struct {
    u16* histo_base;
    u32 histo_size;
    u32* text_start;
    u32* text_end;
} OSProf;
extern void osProfileInit(OSProf*, u32 profcnt);
extern void osProfileStart(u32);
extern void osProfileFlush(void);
extern void osProfileStop(void);
extern void osThreadProfileClear(OSId);
extern void osThreadProfileInit(void);
extern void osThreadProfileStart(void);
extern void osThreadProfileStop(void);
extern u32 osThreadProfileReadCount(OSId);
extern u32 osThreadProfileReadCountTh(OSThread*);
extern OSTime osThreadProfileReadTime(OSId);
extern OSTime osThreadProfileReadTimeTh(OSThread*);
extern s32 osEepromProbe(OSMesgQueue*);
extern s32 osEepromRead(OSMesgQueue*, u8, u8*);
extern s32 osEepromWrite(OSMesgQueue*, u8, u8*);
extern s32 osEepromLongRead(OSMesgQueue*, u8, u8*, int);
extern s32 osEepromLongWrite(OSMesgQueue*, u8, u8*, int);
typedef u32 OSIntMask;
typedef u32 OSHWIntr;
extern OSIntMask osGetIntMask(void);
extern OSIntMask osSetIntMask(OSIntMask);
typedef struct {
    u32 errStatus;
    void* dramAddr;
    void* C2Addr;
    u32 sectorSize;
    u32 C1ErrNum;
    u32 C1ErrSector[4];
} __OSBlockInfo;
typedef struct {
    u32 cmdType;
    u16 transferMode;
    u16 blockNum;
    s32 sectorNum;
    u32 devAddr;
    u32 bmCtlShadow;
    u32 seqCtlShadow;
    __OSBlockInfo block[2];
} __OSTranxInfo;
typedef struct OSPiHandle_s {
    struct OSPiHandle_s* next;
    u8 type;
    u8 latency;
    u8 pageSize;
    u8 relDuration;
    u8 pulse;
    u8 domain;
    u32 baseAddress;
    u32 speed;
    __OSTranxInfo transferInfo;
} OSPiHandle;
typedef struct {
    u8 type;
    u32 address;
} OSPiInfo;
typedef struct {
    u16 type;
    u8 pri;
    u8 status;
    OSMesgQueue* retQueue;
} OSIoMesgHdr;
typedef struct {
    OSIoMesgHdr hdr;
    void* dramAddr;
    u32 devAddr;
    u32 size;
    OSPiHandle* piHandle;
} OSIoMesg;
typedef struct {
    s32 active;
    OSThread* thread;
    OSMesgQueue* cmdQueue;
    OSMesgQueue* evtQueue;
    OSMesgQueue* acsQueue;
    s32 (*dma)(s32, u32, void*, u32);
    s32 (*edma)(OSPiHandle*, s32, u32, void*, u32);
} OSDevMgr;
extern OSPiHandle* __osPiTable;
extern u32 osPiGetStatus(void);
extern s32 osPiGetDeviceType(void);
extern s32 osPiWriteIo(u32, u32);
extern s32 osPiReadIo(u32, u32*);
extern s32 osPiStartDma(OSIoMesg*, s32, s32, u32, void*, u32, OSMesgQueue*);
extern void osCreatePiManager(OSPri, OSMesgQueue*, OSMesg*, s32);
extern OSPiHandle* osCartRomInit(void);
extern OSPiHandle* osLeoDiskInit(void);
extern OSPiHandle* osDriveRomInit(void);
extern s32 osEPiDeviceType(OSPiHandle*, OSPiInfo*);
extern s32 osEPiWriteIo(OSPiHandle*, u32, u32);
extern s32 osEPiReadIo(OSPiHandle*, u32, u32*);
extern s32 osEPiStartDma(OSPiHandle*, OSIoMesg*, s32);
extern s32 osEPiLinkHandle(OSPiHandle*);
extern OSPiHandle* osFlashReInit(u8 latency, u8 pulse, u8 page_size,
                                 u8 rel_duration, u32 start);
extern OSPiHandle* osFlashInit(void);
extern void osFlashReadStatus(u8* flash_status);
extern void osFlashReadId(u32* flash_type, u32* flash_maker);
extern void osFlashClearStatus(void);
extern s32 osFlashAllErase(void);
extern s32 osFlashSectorErase(u32 page_num);
extern s32 osFlashWriteBuffer(OSIoMesg* mb, s32 priority, void* dramAddr,
                              OSMesgQueue* mq);
extern s32 osFlashWriteArray(u32 page_num);
extern s32 osFlashReadArray(OSIoMesg* mb, s32 priority, u32 page_num,
                            void* dramAddr, u32 n_pages, OSMesgQueue* mq);
extern void osFlashChange(u32 flash_num);
extern void osFlashAllEraseThrough(void);
extern void osFlashSectorEraseThrough(u32 page_num);
extern s32 osFlashCheckEraseEnd(void);
typedef struct {
    int status;
    OSMesgQueue* queue;
    int channel;
    u8 id[32];
    u8 label[32];
    int version;
    int dir_size;
    int inode_table;
    int minode_table;
    int dir_table;
    int inode_start_page;
    u8 banks;
    u8 activebank;
} OSPfs;
typedef struct {
    u32 file_size;
    u32 game_code;
    u16 company_code;
    char ext_name[4];
    char game_name[16];
} OSPfsState;
extern s32 osPfsInitPak(OSMesgQueue*, OSPfs*, int);
extern s32 osPfsRepairId(OSPfs*);
extern s32 osPfsInit(OSMesgQueue*, OSPfs*, int);
extern s32 osPfsReFormat(OSPfs*, OSMesgQueue*, int);
extern s32 osPfsChecker(OSPfs*);
extern s32 osPfsAllocateFile(OSPfs*, u16, u32, u8*, u8*, int, s32*);
extern s32 osPfsFindFile(OSPfs*, u16, u32, u8*, u8*, s32*);
extern s32 osPfsDeleteFile(OSPfs*, u16, u32, u8*, u8*);
extern s32 osPfsReadWriteFile(OSPfs*, s32, u8, int, int, u8*);
extern s32 osPfsFileState(OSPfs*, s32, OSPfsState*);
extern s32 osPfsGetLabel(OSPfs*, u8*, int*);
extern s32 osPfsSetLabel(OSPfs*, u8*);
extern s32 osPfsIsPlug(OSMesgQueue*, u8*);
extern s32 osPfsFreeBlocks(OSPfs*, s32*);
extern s32 osPfsNumFiles(OSPfs*, s32*, s32*);
typedef struct {
    u16 fixed1;
    u16 start_address;
    u8 nintendo_chr[0x30];
    u8 game_title[16];
    u16 company_code;
    u8 body_code;
    u8 cart_type;
    u8 rom_size;
    u8 ram_size;
    u8 country_code;
    u8 fixed2;
    u8 version;
    u8 isum;
    u16 sum;
} OSGbpakId;
extern s32 osGbpakInit(OSMesgQueue*, OSPfs*, int);
extern s32 osGbpakPower(OSPfs*, s32);
extern s32 osGbpakGetStatus(OSPfs*, u8*);
extern s32 osGbpakReadWrite(OSPfs*, u16, u16, u8*, u16);
extern s32 osGbpakReadId(OSPfs*, OSGbpakId*, u8*);
extern s32 osGbpakCheckConnector(OSPfs*, u8*);
extern void __osInitialize_common(void);
extern void __osInitialize_autodetect(void);
extern void __osInitialize_msp(void);
extern void __osInitialize_kmc(void);
extern void __osInitialize_isv(void);
extern void __osInitialize_emu(void);
extern s32 osTestHost(void);
extern void osReadHost(void*, u32);
extern void osWriteHost(void*, u32);
extern void osAckRamromRead(void);
extern void osAckRamromWrite(void);
extern void osInitRdb(u8* sendBuf, u32 sendSize);
extern void bcopy(const void*, void*, int);
extern int bcmp(const void*, const void*, int);
extern void bzero(void*, int);
extern int sprintf(char* s, const char* fmt, ...);
extern void osSyncPrintf(const char* fmt, ...);

extern s32 osMotorInit(OSMesgQueue*, OSPfs*, int);
extern s32 osMotorStop(OSPfs*);
extern s32 osMotorStart(OSPfs*);
extern u32 osDpGetStatus(void);
extern void osDpSetStatus(u32);
extern void osDpGetCounters(u32*);
extern s32 osDpSetNextBuffer(void*, u64);
extern u32 osGetCount(void);
extern s32 osRomType;
extern void* osRomBase;
extern s32 osTvType;
extern s32 osResetType;
extern s32 osCicId;
extern s32 osVersion;
extern u32 osMemSize;
extern s32 osAppNMIBuffer[];
extern u64 osClockRate;
extern OSIntMask __OSGlobalIntMask;
extern void osInitialize(void);
extern void osExit(void);
extern u32 osGetMemSize(void);
extern s32 osAfterPreNMI(void);

typedef u32 OSPageMask;
extern void osMapTLB(s32, OSPageMask, void*, u32, u32, s32);
extern void osMapTLBRdb(void);
extern void osUnmapTLB(s32);
extern void osUnmapTLBAll(void);
extern void osSetTLBASID(s32);

typedef struct {
    u32 ctrl;
    u32 width;
    u32 burst;
    u32 vSync;
    u32 hSync;
    u32 leap;
    u32 hStart;
    u32 xScale;
    u32 vCurrent;
} OSViCommonRegs;
typedef struct {
    u32 origin;
    u32 yScale;
    u32 vStart;
    u32 vBurst;
    u32 vIntr;
} OSViFieldRegs;
typedef struct {
    u8 type;
    OSViCommonRegs comRegs;
    OSViFieldRegs fldRegs[2];
} OSViMode;
extern OSViMode osViModeTable[];
extern OSViMode osViModeNtscLpn1;
extern OSViMode osViModeNtscLpf1;
extern OSViMode osViModeNtscLan1;
extern OSViMode osViModeNtscLaf1;
extern OSViMode osViModeNtscLpn2;
extern OSViMode osViModeNtscLpf2;
extern OSViMode osViModeNtscLan2;
extern OSViMode osViModeNtscLaf2;
extern OSViMode osViModeNtscHpn1;
extern OSViMode osViModeNtscHpf1;
extern OSViMode osViModeNtscHan1;
extern OSViMode osViModeNtscHaf1;
extern OSViMode osViModeNtscHpn2;
extern OSViMode osViModeNtscHpf2;
extern OSViMode osViModePalLpn1;
extern OSViMode osViModePalLpf1;
extern OSViMode osViModePalLan1;
extern OSViMode osViModePalLaf1;
extern OSViMode osViModePalLpn2;
extern OSViMode osViModePalLpf2;
extern OSViMode osViModePalLan2;
extern OSViMode osViModePalLaf2;
extern OSViMode osViModePalHpn1;
extern OSViMode osViModePalHpf1;
extern OSViMode osViModePalHan1;
extern OSViMode osViModePalHaf1;
extern OSViMode osViModePalHpn2;
extern OSViMode osViModePalHpf2;
extern OSViMode osViModeMpalLpn1;
extern OSViMode osViModeMpalLpf1;
extern OSViMode osViModeMpalLan1;
extern OSViMode osViModeMpalLaf1;
extern OSViMode osViModeMpalLpn2;
extern OSViMode osViModeMpalLpf2;
extern OSViMode osViModeMpalLan2;
extern OSViMode osViModeMpalLaf2;
extern OSViMode osViModeMpalHpn1;
extern OSViMode osViModeMpalHpf1;
extern OSViMode osViModeMpalHan1;
extern OSViMode osViModeMpalHaf1;
extern OSViMode osViModeMpalHpn2;
extern OSViMode osViModeMpalHpf2;
extern OSViMode osViModeFpalLpn1;
extern OSViMode osViModeFpalLpf1;
extern OSViMode osViModeFpalLan1;
extern OSViMode osViModeFpalLaf1;
extern OSViMode osViModeFpalLpn2;
extern OSViMode osViModeFpalLpf2;
extern OSViMode osViModeFpalLan2;
extern OSViMode osViModeFpalLaf2;
extern OSViMode osViModeFpalHpn1;
extern OSViMode osViModeFpalHpf1;
extern OSViMode osViModeFpalHan1;
extern OSViMode osViModeFpalHaf1;
extern OSViMode osViModeFpalHpn2;
extern OSViMode osViModeFpalHpf2;
extern u32 osViGetStatus(void);
extern u32 osViGetCurrentMode(void);
extern u32 osViGetCurrentLine(void);
extern u32 osViGetCurrentField(void);
extern void* osViGetCurrentFramebuffer(void);
extern void* osViGetNextFramebuffer(void);
extern void osViSetXScale(f32);
extern void osViSetYScale(f32);
extern void osViExtendVStart(u32);
extern void osViSetSpecialFeatures(u32);
extern void osViSetMode(OSViMode*);
extern void osViSetEvent(OSMesgQueue*, OSMesg, u32);
extern void osViSwapBuffer(void*);
extern void osViBlack(u8);
extern void osViFade(u8, u16);
extern void osViRepeatLine(u8);
extern void osCreateViManager(OSPri);
typedef struct {
    OSMesgQueue* __mq;
    int __channel;
    s32 __mode;
    u8 cmd_status;
} OSVoiceHandle;
typedef struct {
    u16 warning;
    u16 answer_num;
    u16 voice_level;
    u16 voice_sn;
    u16 voice_time;
    u16 answer[5];
    u16 distance[5];
} OSVoiceData;
extern s32 osVoiceInit(OSMesgQueue*, OSVoiceHandle*, int);
extern s32 osVoiceCheckWord(u8* data);
extern s32 osVoiceClearDictionary(OSVoiceHandle*, u8);
extern s32 osVoiceControlGain(OSVoiceHandle*, s32, s32);
extern s32 osVoiceSetWord(OSVoiceHandle*, u8*);
extern s32 osVoiceStartReadData(OSVoiceHandle*);
extern s32 osVoiceStopReadData(OSVoiceHandle*);
extern s32 osVoiceGetReadData(OSVoiceHandle*, OSVoiceData*);
extern s32 osVoiceMaskDictionary(OSVoiceHandle*, u8*, int);
extern void osVoiceCountSyllables(u8*, u32*);

typedef struct {
    long type;
    long length;
    long magic;
    char userdata[(((4096) * 6) - (3 * sizeof(long)))];
} RamRomBuffer;

typedef struct _Region_s {
    u8* r_startBufferAddress;
    u8* r_endAddress;
    s32 r_bufferSize;
    s32 r_bufferCount;
    u16 r_freeList;
    u16 r_alignSize;
} OSRegion;
extern void* osCreateRegion(void*, u32, u32, u32);
extern void* osMalloc(void*);
extern void osFree(void*, void*);
extern s32 osGetRegionBufCount(void*);
extern s32 osGetRegionBufSize(void*);
extern void rmonMain(void*);
extern void rmonPrintf(const char*, ...);
struct bitmap {
    s16 width;
    s16 width_img;
    s16 s;
    s16 t;
    void* buf;
    s16 actualHeight;
    s16 LUToffset;
};
typedef struct bitmap Bitmap;
struct sprite {
    s16 x, y;
    s16 width, height;
    f32 scalex, scaley;
    s16 expx, expy;
    u16 attr;
    s16 zdepth;
    u8 red;
    u8 green;
    u8 blue;
    u8 alpha;
    s16 startTLUT;
    s16 nTLUT;
    int* LUT;
    s16 istart;
    s16 istep;
    s16 nbitmaps;
    s16 ndisplist;
    s16 bmheight;
    s16 bmHreal;
    u8 bmfmt;
    u8 bmsiz;
    Bitmap* bitmap;
    Gfx* rsp_dl;
    Gfx* rsp_dl_next;
    s16 frac_s,
        frac_t;
};
typedef struct sprite Sprite;
void spSetAttribute(Sprite* sp, s32 attr);
void spClearAttribute(Sprite* sp, s32 attr);
void spX2Move(Sprite* sp, s32 x, s32 y);
void spScale(Sprite* sp, f32 sx, f32 sy);
void spX2SetZ(Sprite* sp, s32 z);
void spColor(Sprite* sp, u8 red, u8 green, u8 blue, u8 alpha);
Gfx* spX2Draw(Sprite* sp);
void spX2Init(Gfx** glistp);
void spX2Scissor(s32 xmin, s32 xmax, s32 ymin, s32 ymax);
void spX2Finish(Gfx** glistp);

extern long long int rspbootTextStart[], rspbootTextEnd[];
extern long long int gspFast3DTextStart[], gspFast3DTextEnd[];
extern long long int gspFast3DDataStart[], gspFast3DDataEnd[];
extern long long int gspFast3D_dramTextStart[], gspFast3D_dramTextEnd[];
extern long long int gspFast3D_dramDataStart[], gspFast3D_dramDataEnd[];
extern long long int gspFast3D_fifoTextStart[], gspFast3D_fifoTextEnd[];
extern long long int gspFast3D_fifoDataStart[], gspFast3D_fifoDataEnd[];
extern long long int gspF3DNoNTextStart[], gspF3DNoNTextEnd[];
extern long long int gspF3DNoNDataStart[], gspF3DNoNDataEnd[];
extern long long int gspF3DNoN_dramTextStart[];
extern long long int gspF3DNoN_dramTextEnd[];
extern long long int gspF3DNoN_dramDataStart[];
extern long long int gspF3DNoN_dramDataEnd[];
extern long long int gspF3DNoN_fifoTextStart[];
extern long long int gspF3DNoN_fifoTextEnd[];
extern long long int gspF3DNoN_fifoDataStart[];
extern long long int gspF3DNoN_fifoDataEnd[];
extern long long int gspLine3DTextStart[], gspLine3DTextEnd[];
extern long long int gspLine3DDataStart[], gspLine3DDataEnd[];
extern long long int gspLine3D_dramTextStart[], gspLine3D_dramTextEnd[];
extern long long int gspLine3D_dramDataStart[], gspLine3D_dramDataEnd[];
extern long long int gspLine3D_fifoTextStart[], gspLine3D_fifoTextEnd[];
extern long long int gspLine3D_fifoDataStart[], gspLine3D_fifoDataEnd[];
extern long long int gspSprite2DTextStart[], gspSprite2DTextEnd[];
extern long long int gspSprite2DDataStart[], gspSprite2DDataEnd[];
extern long long int gspSprite2D_dramTextStart[], gspSprite2D_dramTextEnd[];
extern long long int gspSprite2D_dramDataStart[], gspSprite2D_dramDataEnd[];
extern long long int gspSprite2D_fifoTextStart[], gspSprite2D_fifoTextEnd[];
extern long long int gspSprite2D_fifoDataStart[], gspSprite2D_fifoDataEnd[];
extern long long int aspMainTextStart[], aspMainTextEnd[];
extern long long int aspMainDataStart[], aspMainDataEnd[];
extern long long int gspF3DEX_fifoTextStart[], gspF3DEX_fifoTextEnd[];
extern long long int gspF3DEX_fifoDataStart[], gspF3DEX_fifoDataEnd[];
extern long long int gspF3DEX_NoN_fifoTextStart[], gspF3DEX_NoN_fifoTextEnd[];
extern long long int gspF3DEX_NoN_fifoDataStart[], gspF3DEX_NoN_fifoDataEnd[];
extern long long int gspF3DLX_fifoTextStart[], gspF3DLX_fifoTextEnd[];
extern long long int gspF3DLX_fifoDataStart[], gspF3DLX_fifoDataEnd[];
extern long long int gspF3DLX_NoN_fifoTextStart[], gspF3DLX_NoN_fifoTextEnd[];
extern long long int gspF3DLX_NoN_fifoDataStart[], gspF3DLX_NoN_fifoDataEnd[];
extern long long int gspF3DLX_Rej_fifoTextStart[], gspF3DLX_Rej_fifoTextEnd[];
extern long long int gspF3DLX_Rej_fifoDataStart[], gspF3DLX_Rej_fifoDataEnd[];
extern long long int gspF3DLP_Rej_fifoTextStart[], gspF3DLP_Rej_fifoTextEnd[];
extern long long int gspF3DLP_Rej_fifoDataStart[], gspF3DLP_Rej_fifoDataEnd[];
extern long long int gspL3DEX_fifoTextStart[], gspL3DEX_fifoTextEnd[];
extern long long int gspL3DEX_fifoDataStart[], gspL3DEX_fifoDataEnd[];
extern long long int gspF3DEX2_fifoTextStart[], gspF3DEX2_fifoTextEnd[];
extern long long int gspF3DEX2_fifoDataStart[], gspF3DEX2_fifoDataEnd[];
extern long long int gspF3DEX2_NoN_fifoTextStart[], gspF3DEX2_NoN_fifoTextEnd[];
extern long long int gspF3DEX2_NoN_fifoDataStart[], gspF3DEX2_NoN_fifoDataEnd[];
extern long long int gspF3DEX2_Rej_fifoTextStart[], gspF3DEX2_Rej_fifoTextEnd[];
extern long long int gspF3DEX2_Rej_fifoDataStart[], gspF3DEX2_Rej_fifoDataEnd[];
extern long long int gspF3DLX2_Rej_fifoTextStart[], gspF3DLX2_Rej_fifoTextEnd[];
extern long long int gspF3DLX2_Rej_fifoDataStart[], gspF3DLX2_Rej_fifoDataEnd[];
extern long long int gspL3DEX2_fifoTextStart[], gspL3DEX2_fifoTextEnd[];
extern long long int gspL3DEX2_fifoDataStart[], gspL3DEX2_fifoDataEnd[];
extern long long int gspF3DEX2_xbusTextStart[], gspF3DEX2_xbusTextEnd[];
extern long long int gspF3DEX2_xbusDataStart[], gspF3DEX2_xbusDataEnd[];
extern long long int gspF3DEX2_NoN_xbusTextStart[], gspF3DEX2_NoN_xbusTextEnd[];
extern long long int gspF3DEX2_NoN_xbusDataStart[], gspF3DEX2_NoN_xbusDataEnd[];
extern long long int gspF3DEX2_Rej_xbusTextStart[], gspF3DEX2_Rej_xbusTextEnd[];
extern long long int gspF3DEX2_Rej_xbusDataStart[], gspF3DEX2_Rej_xbusDataEnd[];
extern long long int gspF3DLX2_Rej_xbusTextStart[], gspF3DLX2_Rej_xbusTextEnd[];
extern long long int gspF3DLX2_Rej_xbusDataStart[], gspF3DLX2_Rej_xbusDataEnd[];
extern long long int gspL3DEX2_xbusTextStart[], gspL3DEX2_xbusTextEnd[];
extern long long int gspL3DEX2_xbusDataStart[], gspL3DEX2_xbusDataEnd[];
typedef void (*OSErrorHandler)(s16, s16, ...);
OSErrorHandler osSetErrorHandler(OSErrorHandler);
typedef struct {
    u32 magic;
    u32 len;
    u32* base;
    s32 startCount;
    s32 writeOffset;
} OSLog;
typedef struct {
    u32 magic;
    u32 timeStamp;
    u16 argCount;
    u16 eventID;
} OSLogItem;
typedef struct {
    u32 magic;
    u32 version;
} OSLogFileHdr;
void osCreateLog(OSLog* log, u32* base, s32 len);
void osLogEvent(OSLog* log, s16 code, s16 numArgs, ...);
void osFlushLog(OSLog* log);
u32 osLogFloat(f32);
extern void osDelay(int count);
typedef struct Vec2 {
    s16 x, y;
} Vec2;
typedef struct Vec2f {
    f32 x, y;
} Vec2f;
typedef struct Vec3 {
    s16 x, y, z;
} Vec3;
typedef struct Vec3f {
    f32 x, y, z;
} Vec3f;
typedef struct Angle {
    s16 pitch, yaw, roll;
} Angle;
typedef f32 Mat4f[4][4];
extern f32 atan2f(f32 arg1, f32 arg2);
extern s16 atan2s(s16 y, s16 x);
f32 func_80011310_11F10(f32 src);
f32 func_80011370_11F70(f32 src);
f32 vec3f_distance(Vec3f* src1, Vec3f* src2);
f32 vec3f_magnitude(Vec3f* src);
f32 vec3f_80011440(Vec3f* dest, Vec3f* src, f32 scalar);
void vec3f_add(Vec3f* dest, Vec3f* src1, Vec3f* src2);
void vec3f_substract(Vec3f* dest, Vec3f* src1, Vec3f* src2);
void vec3f_copy(Vec3f* dest, Vec3f* src);
void vec3f_swap(Vec3f* dest, Vec3f* src);
void vec3f_multiplyScalar(Vec3f* dest, Vec3f* src, f32 scalar);
void vec3f_percentage(Vec3f* dest, Vec3f* src, f32 percent);
void vec3f_complement(Vec3f* dest, Vec3f* src);
f32 vec3f_80011614(Vec3f* dest, Vec3f* src);
f32 vec3f_dotProduct(Vec3f* src1, Vec3f* src2);
void vec3f_crossProduct(Vec3f* dest, Vec3f* src1, Vec3f* src2);
f32 vec3f_80011710(Vec3f* arg0, Vec3f* arg1);
void vec3f_set(Vec3f* vec, f32 x, f32 y, f32 z);
void vec3f_multiplyByOne(Vec3f* dest);
void vec3f_800117a4(Vec3f* dest, Vec3f* src1, Vec3f* src2, f32 scalar);
void vec3f_80011808(Vec3f* dest, Vec3f* src1, Vec3f* src2);
void func_80011880(Vec3f* dest, Vec3f* src, Mat4f* mtx);
void func_80011914_12514(Vec3f* dest, Vec3f* src, Vec3f* rotation, s32 angle);
void func_80011984_12584(Vec3f* arg0, Vec3f* arg1, Vec3f* arg2);
void func_800119F0_125F0(Vec3f* arg0, Vec3f* arg1, Vec3f* arg2, Vec3f* arg3);
extern void vec3f_substractFloats(f32*, f32*, f32*);
f32 f32_trunc(f32 value);
f32 f32_simple_round_nearest(f32 value);
f32 f32_round_nearest_with_sign(f32 value);
f32 f32_normalize(f32 value, f32 min, f32 max);
f32 f32_clamp(f32 value, f32 min, f32 max);
s32 func_80011C6C_1286C(s32 arg0, s32 arg1);

typedef enum NIFileID {
    NI_ASSETS_01 = 0x01,
    NI_ASSETS_DEBUG_FONT = 0x02,
    NI_ASSETS_REINHARDT = 0x03,
    NI_ASSETS_REINHARDT_ALT_COSTUME = 0x04,
    NI_ASSETS_REINHARDT_WHIP = 0x05,
    NI_ASSETS_CARRIE = 0x06,
    NI_ASSETS_CARRIE_ALT_COSTUME = 0x07,
    NI_ASSETS_ENEMY_TARGET_GRAPHIC = 0x08,
    NI_ASSETS_UNUSED_3_HEAD_WOLF = 0x09,
    NI_ASSETS_CERBERUS = 0x0A,
    NI_ASSETS_WHITE_DRAGON = 0x0B,
    NI_ASSETS_GARDENER = 0x0C,
    NI_ASSETS_STONE_DOG = 0x0D,
    NI_ASSETS_BEHEMOTH = 0x0E,
    NI_ASSETS_WERETIGER = 0x0F,
    NI_ASSETS_WEREWOLF = 0x10,
    NI_ASSETS_HELL_KNIGHT = 0x11,
    NI_ASSETS_GHOST = 0x12,
    NI_ASSETS_ICEMAN_PUDDLE = 0x13,
    NI_ASSETS_MUDMAN_LAVAMAN = 0x14,
    NI_ASSETS_BLOOD_JELLY = 0x15,
    NI_ASSETS_ICEMAN = 0x16,
    NI_ASSETS_FIRE_BAT = 0x17,
    NI_ASSETS_FLYING_SKULL = 0x18,
    NI_ASSETS_BAT = 0x19,
    NI_ASSETS_MEDUSA_HEAD = 0x1A,
    NI_ASSETS_PILLAR_OF_BONES = 0x1B,
    NI_ASSETS_UNDEAD_MAIDEN = 0x1C,
    NI_ASSETS_VAMPIRE_MAID = 0x1D,
    NI_ASSETS_VAMPIRE_VILLAGER = 0x1E,
    NI_ASSETS_VAMPIRE_BUTLER = 0x1F,
    NI_ASSETS_VINCENT = 0x20,
    NI_ASSETS_WEREJAGUAR = 0x21,
    NI_ASSETS_SPIDER_CENTAUR = 0x22,
    NI_ASSETS_LIZARD_MAN = 0x23,
    NI_ASSETS_SKELETON_WARRIOR = 0x24,
    NI_ASSETS_GLASS_KNIGHT = 0x25,
    NI_ASSETS_KING_SKELETON = 0x26,
    NI_ASSETS_SKELETON_BIKER = 0x27,
    NI_ASSETS_TRUE_DRACULA = 0x28,
    NI_ASSETS_MALUS = 0x29,
    NI_ASSETS_MALUS_HORSE = 0x2A,
    NI_ASSETS_DEMON_DRACULA = 0x2B,
    NI_ASSETS_VAMPIRE_GILDRE = 0x2C,
    NI_ASSETS_RENON = 0x2D,
    NI_ASSETS_RENON_DEMON = 0x2E,
    NI_ASSETS_DEATH = 0x2F,
    NI_ASSETS_DEMONIC_FISH = 0x30,
    NI_ASSETS_ROSA = 0x31,
    NI_ASSETS_32 = 0x32,
    NI_ASSETS_CAMILLA = 0x33,
    NI_ASSETS_ACTRIESE = 0x34,
    NI_ASSETS_CAMILLA_FIGHT = 0x35,
    NI_ASSETS_36 = 0x36,
    NI_ASSETS_37 = 0x37,
    NI_COMMON_GAMEPLAY_EFFECTS = 0x38,
    NI_ASSETS_39 = 0x39,
    NI_ASSETS_3A = 0x3A,
    NI_ASSETS_3B = 0x3B,
    NI_ASSETS_3C = 0x3C,
    NI_MAP_FOREST_OF_SILENCE = 0x3D,
    NI_MAP_CASTLE_WALL_TOWERS = 0x3E,
    NI_MAP_CASTLE_WALL_MAIN = 0x3F,
    NI_MAP_VILLA_YARD = 0x40,
    NI_MAP_VILLA_FOYER = 0x41,
    NI_MAP_VILLA_HALLWAY = 0x42,
    NI_MAP_VILLA_MAZE_GARDEN = 0x43,
    NI_MAP_TUNNEL = 0x44,
    NI_MAP_UNDERGROUND_WATERWAY = 0x45,
    NI_MAP_CASTLE_CENTER_MAIN = 0x46,
    NI_MAP_CASTLE_CENTER_BOTTOM_ELEVATOR = 0x47,
    NI_MAP_CASTLE_CENTER_LIZARD = 0x48,
    NI_MAP_CASTLE_CENTER_BROKEN_STAIRCASE = 0x49,
    NI_MAP_CASTLE_CENTER_LIBRARY = 0x4A,
    NI_MAP_CASTLE_CENTER_NITRO_ROOM = 0x4B,
    NI_MAP_CASTLE_CENTER_TOP_ELEVATOR_ROOM = 0x4C,
    NI_MAP_TOWER_OF_EXECUTION = 0x4D,
    NI_MAP_TOWER_OF_SORCERY = 0x4E,
    NI_MAP_TOWER_OF_SCIENCE = 0x4F,
    NI_MAP_DUEL_TOWER = 0x50,
    NI_MAP_CASTLE_KEEP_EXTERIOR = 0x51,
    NI_MAP_CASTLE_KEEP = 0x52,
    NI_MAP_INTRO_NARRATION = 0x53,
    NI_MAP_CLOCK_TOWER = 0x54,
    NI_MAP_DRACULA_DESERT = 0x55,
    NI_MAP_ROSE_ACTRICE_MEET_ROOM = 0x56,
    NI_MAP_VILLA_CRYPT_AREA = 0x57,
    NI_MAP_ROOM_OF_CLOCKS = 0x58,
    NI_MAP_ENDING = 0x59,
    NI_ASSETS_PICKABLE_ITEM_ASSETS = 0x5A,
    NI_ASSETS_SKYBOX = 0x5B,
    NI_MAP_TEST_GRID = 0x5C,
    NI_ASSETS_KONAMI_AND_KCEK_LOGOS = 0x5D,
    NI_ASSETS_SCROLL = 0x5E,
    NI_ASSETS_TITLE = 0x5F,
    NI_ASSETS_MENU = 0x60,
    NI_ASSETS_NECRONOMICON = 0x61,
    NI_ASSETS_CHARACTER_SELECTION_SCREEN = 0x62,
    NI_ASSETS_GAMEPLAY_HUD = 0x63,
    NI_ASSETS_GAME_OVER = 0x64,
    NI_ASSETS_FILE_SELECT = 0x65,
    NI_ASSETS_CONTROLLER_BUTTONS = 0x66,
    NI_ASSETS_RENON_BRIEFCASE = 0x67,
    NI_ASSETS_FILM_REEL_CUTSCENE_EFFECT = 0x68,
    NI_ASSETS_CUTSCENE_01 = 0x69,
    NI_ASSETS_CUTSCENE_02 = 0x6A,
    NI_ASSETS_CUTSCENE_2B = 0x6B,
    NI_ASSETS_CUTSCENE_2C = 0x6C,
    NI_ASSETS_CUTSCENE_2E = 0x6D,
    NI_ASSETS_CUTSCENE_3F = 0x6E,
    NI_ASSETS_CUTSCENE_2D = 0x6F,
    NI_ASSETS_CUTSCENE_0A = 0x70,
    NI_ASSETS_SMILEY_FACE = 0x71,
    NI_OVL_CERBERUS = 0x72,
    NI_OVL_WHITE_DRAGON = 0x73,
    NI_OVL_GARDENER = 0x74,
    NI_OVL_STONE_DOG = 0x75,
    NI_OVL_MALUS = 0x76,
    NI_OVL_BEHEMOTH = 0x77,
    NI_OVL_WERETIGER = 0x78,
    NI_OVL_WEREWOLF = 0x79,
    NI_OVL_HELL_KNIGHT = 0x7A,
    NI_OVL_GHOST = 0x7B,
    NI_OVL_ICEMAN = 0x7C,
    NI_OVL_ICEMAN_ASSETS_LOADER = 0x7D,
    NI_OVL_7E = 0x7E,
    NI_OVL_FLYING_SKULL = 0x7F,
    NI_OVL_BAT = 0x80,
    NI_OVL_MEDUSA_HEAD = 0x81,
    NI_OVL_PILLAR_OF_BONES = 0x82,
    NI_OVL_VAMPIRES = 0x83,
    NI_OVL_VINCENT = 0x84,
    NI_OVL_85 = 0x85,
    NI_OVL_86 = 0x86,
    NI_OVL_87 = 0x87,
    NI_OVL_88 = 0x88,
    NI_OVL_89 = 0x89,
    NI_OVL_SPIDER_CENTAUR = 0x8A,
    NI_OVL_LIZARD_MAN = 0x8B,
    NI_OVL_SKELETON_WARRIOR = 0x8C,
    NI_OVL_KING_SKELETON = 0x8D,
    NI_OVL_SKELETON_BIKER = 0x8E,
    NI_OVL_TRUE_DRACULA = 0x8F,
    NI_OVL_90 = 0x90,
    NI_OVL_91 = 0x91,
    NI_OVL_MALUS_CUTSCENE = 0x92,
    NI_OVL_MALUS_HORSE = 0x93,
    NI_OVL_DEMON_DRACULA = 0x94,
    NI_OVL_DEMON_DRACULA_ASSETS_LOADER = 0x95,
    NI_OVL_96 = 0x96,
    NI_OVL_97 = 0x97,
    NI_OVL_VAMPIRE_GILDRE = 0x98,
    NI_OVL_99 = 0x99,
    NI_OVL_RENON_DEMON = 0x9A,
    NI_OVL_DEATH = 0x9B,
    NI_OVL_9C = 0x9C,
    NI_OVL_ROSA = 0x9D,
    NI_OVL_CAMILLA = 0x9E,
    NI_OVL_ACTRISE = 0x9F,
    NI_OVL_A0 = 0xA0,
    NI_OVL_A1 = 0xA1,
    NI_OVL_A2 = 0xA2,
    NI_OVL_A3 = 0xA3,
    NI_OVL_A4 = 0xA4,
    NI_OVL_HELL_KNIGHT_STATIC = 0xA5,
    NI_OVL_A6 = 0xA6,
    NI_OVL_MINI_SCROLL = 0xA7,
    NI_OVL_A8 = 0xA8,
    NI_OVL_GAMENOTE_DELETE_MGR = 0xA9,
    NI_OVL_TITLE_SCREEN = 0xAA,
    NI_OVL_AB = 0xAB,
    NI_OVL_AC = 0xAC,
    NI_OVL_TITLE_DEMO = 0xAD,
    NI_OVL_CREDITSMGR = 0xAE,
    NI_OVL_PAUSE_MENU = 0xAF,
    NI_OVL_CHARACTER_SELECT = 0xB0,
    NI_OVL_GAME_OVER = 0xB1,
    NI_OVL_SAVE_GAME_RESULTS = 0xB2,
    NI_OVL_B3 = 0xB3,
    NI_OVL_SAVE_GAME = 0xB4,
    NI_OVL_TEXTBOX_ADVANCE_ARROW = 0xB5,
    NI_OVL_BUTTON_CONFIG_OPTION_MENU = 0xB6,
    NI_OVL_ENTRANCE_MAP_NAME_DISPLAY = 0xB7,
    NI_OVL_CONTRACTMGR = 0xB8,
    NI_OVL_RENONS_BRIEFCASE = 0xB9,
    NI_OVL_BA = 0xBA,
    NI_OVL_EASY_MODE_ENDING_MSG = 0xBB,
    NI_OVL_BC = 0xBC,
    NI_OVL_NITRO_MANDRAGORA_DISPLAY = 0xBD,
    NI_OVL_BE = 0xBE,
    NI_OVL_BF = 0xBF,
    NI_OVL_C0 = 0xC0,
    NI_OVL_C1 = 0xC1,
    NI_OVL_C2 = 0xC2,
    NI_OVL_FILM_REEL_CUTSCENE_EFFECT = 0xC3,
    NI_OVL_CUTSCENE_01 = 0xC4,
    NI_OVL_CUTSCENE_03 = 0xC5,
    NI_OVL_CUTSCENE_04 = 0xC6,
    NI_OVL_CUTSCENE_05 = 0xC7,
    NI_OVL_CUTSCENE_06 = 0xC8,
    NI_OVL_CUTSCENE_07 = 0xC9,
    NI_OVL_CUTSCENE_08 = 0xCA,
    NI_OVL_CUTSCENE_09 = 0xCB,
    NI_OVL_CUTSCENE_0A = 0xCC,
    NI_OVL_CUTSCENE_0B = 0xCD,
    NI_OVL_CUTSCENE_0C = 0xCE,
    NI_OVL_CUTSCENE_0D = 0xCF,
    NI_OVL_CUTSCENE_0E = 0xD0,
    NI_OVL_CUTSCENE_0F = 0xD1,
    NI_OVL_CUTSCENE_10 = 0xD2,
    NI_OVL_CUTSCENE_11 = 0xD3,
    NI_OVL_CUTSCENE_12 = 0xD4,
    NI_OVL_CUTSCENE_13 = 0xD5,
    NI_OVL_CUTSCENE_14 = 0xD6,
    NI_OVL_CUTSCENE_15 = 0xD7,
    NI_OVL_CUTSCENE_16 = 0xD8,
    NI_OVL_CUTSCENE_17 = 0xD9,
    NI_OVL_CUTSCENE_18 = 0xDA,
    NI_OVL_CUTSCENE_19 = 0xDB,
    NI_OVL_CUTSCENE_1A = 0xDC,
    NI_OVL_CUTSCENE_1B = 0xDD,
    NI_OVL_CUTSCENE_1C = 0xDE,
    NI_OVL_CUTSCENE_1E = 0xDF,
    NI_OVL_CUTSCENE_1F = 0xE0,
    NI_OVL_CUTSCENE_21 = 0xE1,
    NI_OVL_CUTSCENE_22 = 0xE2,
    NI_OVL_CUTSCENE_23 = 0xE3,
    NI_OVL_CUTSCENE_24 = 0xE4,
    NI_OVL_CUTSCENE_25 = 0xE5,
    NI_OVL_CUTSCENE_26 = 0xE6,
    NI_OVL_CUTSCENE_27 = 0xE7,
    NI_OVL_CUTSCENE_28 = 0xE8,
    NI_OVL_CUTSCENE_29 = 0xE9,
    NI_OVL_CUTSCENE_2A = 0xEA,
    NI_OVL_CUTSCENE_2B = 0xEB,
    NI_OVL_CUTSCENE_2C = 0xEC,
    NI_OVL_CUTSCENE_2D = 0xED,
    NI_OVL_CUTSCENE_2E = 0xEE,
    NI_OVL_CUTSCENE_32 = 0xEF,
    NI_OVL_CUTSCENE_33 = 0xF0,
    NI_OVL_CUTSCENE_34 = 0xF1,
    NI_OVL_CUTSCENE_35 = 0xF2,
    NI_OVL_CUTSCENE_3C = 0xF3,
    NI_OVL_CUTSCENE_3D = 0xF4,
    NI_OVL_CUTSCENE_3E = 0xF5,
    NI_OVL_CUTSCENE_3F = 0xF6,
    NI_OVL_CUTSCENE_44 = 0xF7,
    NI_OVL_CUTSCENE_45 = 0xF8,
    NI_OVL_CUTSCENE_52 = 0xF9,
    NI_OVL_CUTSCENE_54 = 0xFA,
    NI_OVL_CUTSCENE_55 = 0xFB,
    NI_OVL_CUTSCENE_56 = 0xFC,
    NI_OVL_CUTSCENE_57 = 0xFD,
    NI_OVL_CUTSCENE_63 = 0xFE
} NIFileID;
extern u32 NisitenmaIchigo_checkAndStoreLoadedFile(u32 file_ID);
extern void* NisitenmaIchigoFiles_segmentToVirtual(u32 segment_address, s32 file_ID);
typedef u8 UNK8;
typedef u16 UNK16;
typedef s32 UNK32;
typedef void* UNKPTR;
typedef u8 Addr[];
extern u32 D_80092F50;
extern Gfx* gDisplayListHead;
extern u32 map_misc_event_flags;
extern u16 item_pickables_text[];
extern u32 map_text_segment_address[28];
extern u32 dont_update_map_lighting;
typedef enum TimeOfDay {
    TIME_DAY,
    TIME_EVENING_MORNING,
    TIME_NIGHT
} TimeOfDay;
typedef enum cv64_moon_visibility {
    MOON_VISIBILITY_DAY = 0,
    MOON_VISIBILITY_NIGHT = 1,
    MOON_VISIBILITY_NEW_MOON = 2
} cv64_moon_visibility_t;
typedef union {
    struct {
        s16 moonVisibility;
        s16 dontUpdateMoonVisibility;
    };
    s32 integer;
} union_moonVisibilityVars;
extern union_moonVisibilityVars moonVisibilityVars;
typedef enum MenuID {
    MENU_ID_NOT_ON_MENU = 0,
    MENU_ID_PAUSE = 9,
    MENU_ID_RENON_SHOP = 10,
    MENU_ID_GAME_OVER = 14
} MenuID;
extern void end_master_display_list(void);
extern s32 menuButton_selectNextOption(s32* option, s16* param_2, s16 number_of_options);
extern void func_800010A0_1CA0(void);
extern void func_8001248C_1308C(void);
extern void func_8000C6D0(void);
extern void updateGameSound(void);
extern void drawFog(void);
extern void func_80005658(void);
extern u32 getMapEventFlagID(s16 stage_ID);
s32 func_8001A250_1AE50(s32* arg0, u16* arg1, s16 arg2);
extern void func_80066400(s32);
extern void Map_SetCameraParams(void);
extern void player_status_init(void);
extern const u32 MENU_RED_BACKGROUND_DL;


typedef union RGBA {
    u32 integer;
    struct {
        u8 r, g, b, a;
    };
} RGBA;

enum HierarchyNodeFlag {
    ALLOW_CHANGING_TEXTURE_AND_PALETTE = (1 << (13)),
    CREATE_NEXT_NODE = (1 << (14)),
    DONT_CREATE_SIBLING = (1 << (15))
};
typedef u16 HierarchyNodeFlags;
typedef struct HierarchyNode {
    u32 dlist;
    HierarchyNodeFlags flags;
    Vec3 position;
} HierarchyNode;
typedef struct Hierarchy {
    NIFileID assets_file;
    HierarchyNode nodes[];
} Hierarchy;


typedef struct CollisionTri {
    union {
        u8 type;
        u8 variable;
        u16 type_and_variable;
    };
    Vec3 vtx_pos[3];
} CollisionTri;

typedef struct MapActorModel {
    CollisionTri* collision;
    void* field_0x04;
    void* field_0x08;
    u32 dlist;
    s16 field_0x10;
    u16 total_number_of_collision_triangles;
    s16 file_ID;
    Vec3 field_0x16;
} MapActorModel;
extern MapActorModel* getMapActorModelEntryFromArray(u32 segment_address, s32 file_ID);


enum FigureFlag {
    FIG_FLAG_LOOK_AT_CAMERA_PITCH = (1 << (5)),
    FIG_FLAG_LOOK_AT_CAMERA_YAW = (1 << (6)),
    FIG_FLAG_0080 = (1 << (7)),
    FIG_FLAG_APPLY_FOG_COLOR = (1 << (8)),
    FIG_FLAG_APPLY_BLEND_COLOR = (1 << (9)),
    FIG_FLAG_APPLY_ENVIRONMENT_COLOR = (1 << (10)),
    FIG_FLAG_APPLY_PRIMITIVE_COLOR = (1 << (11)),
    FIG_FLAG_PAUSE_TRANSFORMATIONS = (1 << (14))
};
typedef struct FigureHeader {
    s16 type;
    u16 flags;
    struct FigureHeader* prev;
    struct FigureHeader* sibling;
    struct FigureHeader* next;
    struct FigureHeader* parent;
} FigureHeader;
typedef struct Figure {
    FigureHeader header;
    u8 field_0x14[0xA8 - sizeof(FigureHeader)];
} Figure;
extern FigureHeader* fig_allocate(s16 type);
extern void clearAllFigs(void);
extern void Figure_Update();
extern void Figure_UpdateMatrices();
extern void figure_showModelAndChildren(FigureHeader*, u16);
extern void figure_hideSelfAndChildren(FigureHeader*, u16);
extern FigureHeader* figure_setChild(FigureHeader* new_child, FigureHeader* self);
extern FigureHeader* Figure_SetSibling(FigureHeader* new_sibling, FigureHeader* self);
extern void figure_destroySelfAndChildren_2(FigureHeader*, u16);
extern Figure figures_array[512];
typedef struct {
    u32 field_0x00;
    Figure* field_0x04;
    f32 far;
    u8 field_0x0C[4];
    struct struct_106* field_0x10;
    struct struct_106* field_0x14;
} struct_106;
extern struct_106 D_8034D2B8[256];


typedef struct GraphicContainerHeader {
    void* field_0x00;
    void* data_ptrs[2];
    u8 field_0x0C[4];
} GraphicContainerHeader;

typedef enum HeapKind {
    HEAP_KIND_MULTIPURPOSE,
    HEAP_KIND_1,
    HEAP_KIND_MENU_DATA,
    HEAP_KIND_3,
    HEAP_KIND_4,
    HEAP_KIND_5,
    HEAP_KIND_6,
    HEAP_KIND_MAP_DATA
} HeapKind;
typedef enum HeapBlockFlag {
    HEAP_BLOCK_FREE = 0x0000,
    HEAP_BLOCK_GRAPHIC_CONTAINER = 0x4000,
    HEAP_BLOCK_ACTIVE = 0x8000
} HeapBlockFlag;
typedef enum HeapFlag {
    HEAP_INACTIVE = 0x0000,
    HEAP_WRITE_BACK_CACHE_TO_RAM = 0x4000,
    HEAP_ACTIVE = 0x8000
} HeapFlag;
typedef struct HeapBlockHeader {
    s16 flags;
    u8 field_0x02[2];
    u32 size;
    GraphicContainerHeader graphic_container;
} HeapBlockHeader;
typedef struct Heap {
    s16 flags;
    u8 field_0x02[2];
    u32 size;
    HeapBlockHeader* heap_start;
} Heap;
extern Heap heaps[8];
extern void* HEAP_MULTIPURPOSE_START;
extern void* HEAP_MENU_DATA_START;
extern void memory_copy(void* src, void* dest, u32 size);
extern void memory_clear(void* ptr, u32 length);
void heap_init(
    HeapKind kind, HeapBlockHeader* first_block_ptr, s32 heap_size, u32 additional_flags
);
void heap_free(HeapKind kind);
void heap_writebackDCache(void);
void initHeaps(void);
void* heap_alloc(HeapKind kind, u32 data_size);
extern void* heap_allocWithAlignment(HeapKind kind, u32 data_size, u32 alignment);
extern s32 heapBlock_updateBlockMaxSize(void* data, u32 size);
void heapBlock_free(void* ptr);
void* allocStruct(const char* name, u32 size);
void func_8013B4F0_BE6E0(void);
u32 isMenuDataHeapActive(void);
void func_80000D68_1968(HeapKind arg0, u32 arg1);
GraphicContainerHeader* GraphicContainer_Alloc(HeapKind heap_kind, u32 size);
GraphicContainerHeader* allocGraphicContainerStruct(const char* name, u32 size);
void GraphicContainer_Free(void* ptr);

enum ObjectKind {
    OBJ_KIND_NONE = 0x00,
    OBJ_KIND_MOVE_ALONGSIDE_COLLISION = 0x08,
    OBJ_KIND_ENABLE_COLLISION = 0x10,
    OBJ_KIND_MAP_OVERLAY = 0x20,
    OBJ_KIND_DESTROY = 0x80
};
enum ObjectFlag {
    OBJ_FLAG_NONE = 0x0000,
    OBJ_FLAG_MOVE_ALONGSIDE_COLLISION = 0x0800,
    OBJ_FLAG_ENABLE_COLLISION = 0x1000,
    OBJ_FLAG_MAP_OVERLAY = 0x2000,
    OBJ_FLAG_DESTROY = 0x8000,
    OBJ_TYPE_DATA = 0x8000
};
enum ObjectRawID {
    ID_GAMESTATEMGR = 0x001,
    ID_OBJECT_002 = 0x002,
    ID_OBJECT_003 = 0x003,
    ID_DMAMGR = 0x004,
    ID_GAMEPLAYMGR = 0x005,
    ID_MAP_OBJECT_PARENT = 0x006,
    ID_PLAYER_CONTROLLER = 0x007,
    ID_MAP_SETUP = 0x008,
    ID_ENEMY_PARENT = 0x009,
    ID_GAMENOTE_DELETE_MGR_CREATOR = 0x00A,
    ID_GAMENOTE_DELETE = 0x00B,
    ID_GAMENOTE_DELETE_MGR = 0x00C,
    ID_KONAMI_KCEK_LOGOS_CREATOR = 0x00D,
    ID_KONAMI_KCEK_LOGOS = 0x00E,
    ID_TITLE_SCREEN_TEXT_MGR = 0x00F,
    ID_OPENING_CREATOR = 0x010,
    ID_OPENING = 0x011,
    ID_TITLE_SCREEN_CREATOR = 0x012,
    ID_TITLE_SCREEN = 0x013,
    ID_FILE_SELECT_CREATOR = 0x014,
    ID_FILE_SELECT_MGR = 0x015,
    ID_OPTIONS_CREATOR = 0x016,
    ID_OPTIONS = 0x017,
    ID_TITLE_DEMO_CREATOR = 0x018,
    ID_TITLE_DEMO = 0x019,
    ID_CREDITSMGR_CREATOR = 0x01A,
    ID_CREDITSMGR = 0x01B,
    ID_OBJECT_01C = 0x01C,
    ID_GAME_OVER_CREATOR = 0x01D,
    ID_GAME_OVER = 0x01E,
    ID_OBJECT_01F = 0x01F,
    ID_OBJECT_020 = 0x020,
    ID_MANDRAGORA_TEXTBOX = 0x021,
    ID_NITRO_TEXTBOX = 0x022,
    ID_NITRO_DISPOSAL_TEXTBOX = 0x023,
    ID_EXPLOSIVE_WALL_SPOT = 0x024,
    ID_BOTTOM_ELEVATOR_ACTIVATOR_TEXTBOX = 0x025,
    ID_LIBRARY_PUZZLE = 0x026,
    ID_INTERACTABLES = 0x027,
    ID_OBJECT_028 = 0x028,
    ID_CUTSCENE_TRIGGER = 0x029,
    ID_CUTSCENEMGR = 0x02A,
    ID_CS_FILM_REEL = 0x02B,
    ID_OBJECT_02C = 0x02C,
    ID_OBJECT_02D = 0x02D,
    ID_OBJECT_02E = 0x02E,
    ID_OBJECT_02F = 0x02F,
    ID_OBJECT_030 = 0x030,
    ID_OBJECT_031 = 0x031,
    ID_OBJECT_032 = 0x032,
    ID_OBJECT_033 = 0x033,
    ID_OBJECT_034 = 0x034,
    ID_OBJECT_035 = 0x035,
    ID_OBJECT_036 = 0x036,
    ID_OBJECT_037 = 0x037,
    ID_OBJECT_038 = 0x038,
    ID_OBJECT_039 = 0x039,
    ID_OBJECT_03A = 0x03A,
    ID_OBJECT_03B = 0x03B,
    ID_OBJECT_03C = 0x03C,
    ID_OBJECT_03D = 0x03D,
    ID_OBJECT_03E = 0x03E,
    ID_OBJECT_03F = 0x03F,
    ID_OBJECT_040 = 0x040,
    ID_OBJECT_041 = 0x041,
    ID_OBJECT_042 = 0x042,
    ID_OBJECT_043 = 0x043,
    ID_OBJECT_044 = 0x044,
    ID_OBJECT_045 = 0x045,
    ID_OBJECT_046 = 0x046,
    ID_OBJECT_047 = 0x047,
    ID_OBJECT_048 = 0x048,
    ID_OBJECT_049 = 0x049,
    ID_OBJECT_04A = 0x04A,
    ID_OBJECT_04B = 0x04B,
    ID_OBJECT_04C = 0x04C,
    ID_OBJECT_04D = 0x04D,
    ID_OBJECT_04E = 0x04E,
    ID_OBJECT_04F = 0x04F,
    ID_OBJECT_050 = 0x050,
    ID_OBJECT_051 = 0x051,
    ID_OBJECT_052 = 0x052,
    ID_OBJECT_053 = 0x053,
    ID_OBJECT_054 = 0x054,
    ID_OBJECT_055 = 0x055,
    ID_OBJECT_056 = 0x056,
    ID_OBJECT_057 = 0x057,
    ID_OBJECT_058 = 0x058,
    ID_CUTSCENE_UNUSED_DEATH = 0x059,
    ID_OBJECT_05A = 0x05A,
    ID_OBJECT_05B = 0x05B,
    ID_OBJECT_05C = 0x05C,
    ID_CUTSCENE_FOREST_INTRO = 0x05D,
    ID_OBJECT_05E = 0x05E,
    ID_OBJECT_05F = 0x05F,
    ID_OBJECT_060 = 0x060,
    ID_OBJECT_061 = 0x061,
    ID_OBJECT_062 = 0x062,
    ID_OBJECT_063 = 0x063,
    ID_OBJECT_064 = 0x064,
    ID_OBJECT_065 = 0x065,
    ID_OBJECT_066 = 0x066,
    ID_OBJECT_067 = 0x067,
    ID_CUTSCENE_CREDITS = 0x068,
    ID_DISTORTION = 0x069,
    ID_CAMERAMGR = 0x06A,
    ID_OBJECT_06B = 0x06B,
    ID_PLAYER_CAMERA_CONTROLLER = 0x06C,
    ID_MASTER_LIGHT_MGR = 0x06D,
    ID_MODEL_LIGHTING = 0x06E,
    ID_POINT_LIGHT = 0x06F,
    ID_REINHARDT = 0x070,
    ID_REINHARDT_ALT = 0x071,
    ID_REINHARDT_ATTACKMGR = 0x072,
    ID_REINHARDT_DYNAMIC_SCARF = 0x073,
    ID_CARRIE = 0x074,
    ID_CARRIE_ALT = 0x075,
    ID_CARRIE_ATTACKMGR = 0x076,
    ID_CARRIE_DYNAMIC_SKIRT = 0x077,
    ID_CARRIE_DYNAMIC_RIGHT_STRIP = 0x078,
    ID_CARRIE_DYNAMIC_LEFT_STRIP = 0x079,
    ID_ENEMY_TARGET_GFX = 0x07A,
    ID_OBJECT_07B = 0x07B,
    ID_OBJECT_07C = 0x07C,
    ID_OBJECT_07D = 0x07D,
    ID_OBJECT_07E = 0x07E,
    ID_OBJECT_07F = 0x07F,
    ID_OBJECT_080 = 0x080,
    ID_OBJECT_081 = 0x081,
    ID_OBJECT_082 = 0x082,
    ID_OBJECT_083 = 0x083,
    ID_OBJECT_084 = 0x084,
    ID_OBJECT_085 = 0x085,
    ID_OBJECT_086 = 0x086,
    ID_OBJECT_087 = 0x087,
    ID_OBJECT_088 = 0x088,
    ID_OBJECT_089 = 0x089,
    ID_OBJECT_08A = 0x08A,
    ID_OBJECT_08B = 0x08B,
    ID_OBJECT_08C = 0x08C,
    ID_OBJECT_08D = 0x08D,
    ID_OBJECT_08E = 0x08E,
    ID_OBJECT_08F = 0x08F,
    ID_GARDENER = 0x090,
    ID_OBJECT_091 = 0x091,
    ID_OBJECT_092 = 0x092,
    ID_OBJECT_093 = 0x093,
    ID_OBJECT_094 = 0x094,
    ID_DEATH = 0x095,
    ID_OBJECT_096 = 0x096,
    ID_OBJECT_097 = 0x097,
    ID_OBJECT_098 = 0x098,
    ID_OBJECT_099 = 0x099,
    ID_OBJECT_09A = 0x09A,
    ID_OBJECT_09B = 0x09B,
    ID_OBJECT_09C = 0x09C,
    ID_OBJECT_09D = 0x09D,
    ID_OBJECT_09E = 0x09E,
    ID_OBJECT_09F = 0x09F,
    ID_OBJECT_0A0 = 0x0A0,
    ID_OBJECT_0A1 = 0x0A1,
    ID_OBJECT_0A2 = 0x0A2,
    ID_MUD_MAN_ASSETS_LOADER = 0x0A3,
    ID_BLOOD_MAN_ASSETS_LOADER = 0x0A4,
    ID_ICE_MAN_ASSETS_LOADER = 0x0A5,
    ID_OPENING_BAT = 0x0A6,
    ID_OBJECT_0A7 = 0x0A7,
    ID_OBJECT_0A8 = 0x0A8,
    ID_OBJECT_0A9 = 0x0A9,
    ID_OBJECT_0AA = 0x0AA,
    ID_OBJECT_0AB = 0x0AB,
    ID_OBJECT_0AC = 0x0AC,
    ID_OBJECT_0AD = 0x0AD,
    ID_OBJECT_0AE = 0x0AE,
    ID_OBJECT_0AF = 0x0AF,
    ID_OBJECT_0B0 = 0x0B0,
    ID_OBJECT_0B1 = 0x0B1,
    ID_OBJECT_0B2 = 0x0B2,
    ID_OBJECT_0B3 = 0x0B3,
    ID_OBJECT_0B4 = 0x0B4,
    ID_OBJECT_0B5 = 0x0B5,
    ID_OBJECT_0B6 = 0x0B6,
    ID_DEMON_DRACULA_ASSETS_LOADER = 0x0B7,
    ID_OBJECT_0B8 = 0x0B8,
    ID_OBJECT_0B9 = 0x0B9,
    ID_OBJECT_0BA = 0x0BA,
    ID_OBJECT_0BB = 0x0BB,
    ID_OBJECT_0BC = 0x0BC,
    ID_OBJECT_0BD = 0x0BD,
    ID_OBJECT_0BE = 0x0BE,
    ID_OBJECT_0BF = 0x0BF,
    ID_EFFECTMGR = 0x0C0,
    ID_FIRE = 0x0C1,
    ID_OBJECT_0C2 = 0x0C2,
    ID_OBJECT_0C3 = 0x0C3,
    ID_OBJECT_0C4 = 0x0C4,
    ID_OBJECT_0C5 = 0x0C5,
    ID_OBJECT_0C6 = 0x0C6,
    ID_OBJECT_0C7 = 0x0C7,
    ID_OBJECT_0C8 = 0x0C8,
    ID_OBJECT_0C9 = 0x0C9,
    ID_OBJECT_0CA = 0x0CA,
    ID_OBJECT_0CB = 0x0CB,
    ID_OBJECT_0CC = 0x0CC,
    ID_OBJECT_0CD = 0x0CD,
    ID_OBJECT_0CE = 0x0CE,
    ID_OBJECT_0CF = 0x0CF,
    ID_OBJECT_0D0 = 0x0D0,
    ID_OBJECT_0D1 = 0x0D1,
    ID_OBJECT_0D2 = 0x0D2,
    ID_OBJECT_0D3 = 0x0D3,
    ID_OBJECT_0D4 = 0x0D4,
    ID_OBJECT_0D5 = 0x0D5,
    ID_OBJECT_0D6 = 0x0D6,
    ID_OBJECT_0D7 = 0x0D7,
    ID_OBJECT_0D8 = 0x0D8,
    ID_OBJECT_0D9 = 0x0D9,
    ID_OBJECT_0DA = 0x0DA,
    ID_OBJECT_0DB = 0x0DB,
    ID_OBJECT_0DC = 0x0DC,
    ID_OBJECT_0DD = 0x0DD,
    ID_OBJECT_0DE = 0x0DE,
    ID_OBJECT_0DF = 0x0DF,
    ID_FIRE_SPARKLES = 0x0E0,
    ID_OBJECT_0E1 = 0x0E1,
    ID_OBJECT_0E2 = 0x0E2,
    ID_OBJECT_0E3 = 0x0E3,
    ID_OBJECT_0E4 = 0x0E4,
    ID_PICKABLE_ITEM_FLASH = 0x0E5,
    ID_OBJECT_0E6 = 0x0E6,
    ID_OBJECT_0E7 = 0x0E7,
    ID_OBJECT_0E8 = 0x0E8,
    ID_OBJECT_0E9 = 0x0E9,
    ID_OBJECT_0EA = 0x0EA,
    ID_OBJECT_0EB = 0x0EB,
    ID_OBJECT_0EC = 0x0EC,
    ID_OBJECT_0ED = 0x0ED,
    ID_OBJECT_0EE = 0x0EE,
    ID_OBJECT_0EF = 0x0EF,
    ID_OBJECT_0F0 = 0x0F0,
    ID_OBJECT_0F1 = 0x0F1,
    ID_OBJECT_0F2 = 0x0F2,
    ID_OBJECT_0F3 = 0x0F3,
    ID_OBJECT_0F4 = 0x0F4,
    ID_OBJECT_0F5 = 0x0F5,
    ID_OBJECT_0F6 = 0x0F6,
    ID_OBJECT_0F7 = 0x0F7,
    ID_OBJECT_0F8 = 0x0F8,
    ID_OBJECT_0F9 = 0x0F9,
    ID_OBJECT_0FA = 0x0FA,
    ID_OBJECT_0FB = 0x0FB,
    ID_OBJECT_0FC = 0x0FC,
    ID_OBJECT_0FD = 0x0FD,
    ID_OBJECT_0FE = 0x0FE,
    ID_OBJECT_0FF = 0x0FF,
    ID_OBJECT_100 = 0x100,
    ID_OBJECT_101 = 0x101,
    ID_OBJECT_102 = 0x102,
    ID_OBJECT_103 = 0x103,
    ID_OBJECT_104 = 0x104,
    ID_OBJECT_105 = 0x105,
    ID_OBJECT_106 = 0x106,
    ID_OBJECT_107 = 0x107,
    ID_OBJECT_108 = 0x108,
    ID_OBJECT_109 = 0x109,
    ID_OBJECT_10A = 0x10A,
    ID_OBJECT_10B = 0x10B,
    ID_OBJECT_10C = 0x10C,
    ID_OBJECT_10D = 0x10D,
    ID_OBJECT_10E = 0x10E,
    ID_OBJECT_10F = 0x10F,
    ID_OBJECT_110 = 0x110,
    ID_OBJECT_111 = 0x111,
    ID_OBJECT_112 = 0x112,
    ID_OBJECT_113 = 0x113,
    ID_OBJECT_114 = 0x114,
    ID_OBJECT_115 = 0x115,
    ID_OBJECT_116 = 0x116,
    ID_OBJECT_117 = 0x117,
    ID_OBJECT_118 = 0x118,
    ID_OBJECT_119 = 0x119,
    ID_OBJECT_11A = 0x11A,
    ID_OBJECT_11B = 0x11B,
    ID_OBJECT_11C = 0x11C,
    ID_OBJECT_11D = 0x11D,
    ID_OBJECT_11E = 0x11E,
    ID_OBJECT_11F = 0x11F,
    ID_OBJECT_120 = 0x120,
    ID_OBJECT_121 = 0x121,
    ID_OBJECT_122 = 0x122,
    ID_OBJECT_123 = 0x123,
    ID_OBJECT_124 = 0x124,
    ID_OBJECT_125 = 0x125,
    ID_GAMEPLAY_MENUMGR = 0x126,
    ID_MFDS = 0x127,
    ID_LENS = 0x128,
    ID_HUD = 0x129,
    ID_RENON_SHOP = 0x12A,
    ID_OBJECT_12B = 0x12B,
    ID_OPTIONS_CONTROLLER = 0x12C,
    ID_FILE_SELECT_CONTROLLER = 0x12D,
    ID_CHARACTER_SELECT = 0x12E,
    ID_OBJECT_12F = 0x12F,
    ID_NECRONOMICON = 0x130,
    ID_PAGE = 0x131,
    ID_SCROLL = 0x132,
    ID_MARK = 0x133,
    ID_PAUSE = 0x134,
    ID_OBJECT_135 = 0x135,
    ID_OBJECT_136 = 0x136,
    ID_SAVEGAME = 0x137,
    ID_TEXTBOX_ADVANCE_ARROW = 0x138,
    ID_OBJECT_139 = 0x139,
    ID_ENTRANCE_MAP_NAME_DISPLAY = 0x13A,
    ID_CONTRACTMGR = 0x13B,
    ID_RENON_BRIEFCASE = 0x13C,
    ID_OBJECT_13D = 0x13D,
    ID_MINI_SCROLL = 0x13E,
    ID_OBJECT_13F = 0x13F,
    ID_EASY_ENDING = 0x140,
    ID_STAGE_SELECT = 0x141,
    ID_OBJECT_142 = 0x142,
    ID_OBJECT_143 = 0x143,
    ID_OBJECT_144 = 0x144,
    ID_OBJECT_145 = 0x145,
    ID_OBJECT_146 = 0x146,
    ID_OBJECT_147 = 0x147,
    ID_OBJECT_148 = 0x148,
    ID_OBJECT_149 = 0x149,
    ID_OBJECT_14A = 0x14A,
    ID_OBJECT_14B = 0x14B,
    ID_OBJECT_14C = 0x14C,
    ID_OBJECT_14D = 0x14D,
    ID_OBJECT_14E = 0x14E,
    ID_OBJECT_14F = 0x14F,
    ID_OBJECT_150 = 0x150,
    ID_OBJECT_151 = 0x151,
    ID_OBJECT_152 = 0x152,
    ID_OBJECT_153 = 0x153,
    ID_OBJECT_154 = 0x154,
    ID_OBJECT_155 = 0x155,
    ID_OBJECT_156 = 0x156,
    ID_OBJECT_157 = 0x157,
    ID_OBJECT_158 = 0x158,
    ID_OBJECT_159 = 0x159,
    ID_OBJECT_15A = 0x15A,
    ID_OBJECT_15B = 0x15B,
    ID_OBJECT_15C = 0x15C,
    ID_OBJECT_15D = 0x15D,
    ID_OBJECT_15E = 0x15E,
    ID_OBJECT_15F = 0x15F,
    ID_OBJECT_160 = 0x160,
    ID_OBJECT_161 = 0x161,
    ID_OBJECT_162 = 0x162,
    ID_OBJECT_163 = 0x163,
    ID_OBJECT_164 = 0x164,
    ID_OBJECT_165 = 0x165,
    ID_OBJECT_166 = 0x166,
    ID_OBJECT_167 = 0x167,
    ID_OBJECT_168 = 0x168,
    ID_OBJECT_169 = 0x169,
    ID_LOADING_ZONE = 0x16A,
    ID_OBJECT_16B = 0x16B,
    ID_OBJECT_16C = 0x16C,
    ID_OBJECT_16D = 0x16D,
    ID_OBJECT_16E = 0x16E,
    ID_LEVER = 0x16F,
    ID_OBJECT_170 = 0x170,
    ID_OBJECT_171 = 0x171,
    ID_OBJECT_172 = 0x172,
    ID_COMMON_MOON = 0x173,
    ID_OBJECT_174 = 0x174,
    ID_OBJECT_175 = 0x175,
    ID_OBJECT_176 = 0x176,
    ID_OBJECT_177 = 0x177,
    ID_OBJECT_178 = 0x178,
    ID_OBJECT_179 = 0x179,
    ID_OBJECT_17A = 0x17A,
    ID_OBJECT_17B = 0x17B,
    ID_OBJECT_17C = 0x17C,
    ID_OBJECT_17D = 0x17D,
    ID_OBJECT_17E = 0x17E,
    ID_OBJECT_17F = 0x17F,
    ID_OBJECT_180 = 0x180,
    ID_OBJECT_181 = 0x181,
    ID_OBJECT_182 = 0x182,
    ID_OBJECT_183 = 0x183,
    ID_OBJECT_184 = 0x184,
    ID_OBJECT_185 = 0x185,
    ID_OBJECT_186 = 0x186,
    ID_OBJECT_187 = 0x187,
    ID_OBJECT_188 = 0x188,
    ID_OBJECT_189 = 0x189,
    ID_OBJECT_18A = 0x18A,
    ID_OBJECT_18B = 0x18B,
    ID_OBJECT_18C = 0x18C,
    ID_OBJECT_18D = 0x18D,
    ID_OBJECT_18E = 0x18E,
    ID_OBJECT_18F = 0x18F,
    ID_OBJECT_190 = 0x190,
    ID_OBJECT_191 = 0x191,
    ID_OBJECT_192 = 0x192,
    ID_OBJECT_193 = 0x193,
    ID_OBJECT_194 = 0x194,
    ID_OBJECT_195 = 0x195,
    ID_OBJECT_196 = 0x196,
    ID_OBJECT_197 = 0x197,
    ID_OBJECT_198 = 0x198,
    ID_OBJECT_199 = 0x199,
    ID_OBJECT_19A = 0x19A,
    ID_OBJECT_19B = 0x19B,
    ID_OBJECT_19C = 0x19C,
    ID_OBJECT_19D = 0x19D,
    ID_OBJECT_19E = 0x19E,
    ID_OBJECT_19F = 0x19F,
    ID_OBJECT_1A0 = 0x1A0,
    ID_OBJECT_1A1 = 0x1A1,
    ID_OBJECT_1A2 = 0x1A2,
    ID_OBJECT_1A3 = 0x1A3,
    ID_OBJECT_1A4 = 0x1A4,
    ID_OBJECT_1A5 = 0x1A5,
    ID_OBJECT_1A6 = 0x1A6,
    ID_OBJECT_1A7 = 0x1A7,
    ID_OBJECT_1A8 = 0x1A8,
    ID_OBJECT_1A9 = 0x1A9,
    ID_OBJECT_1AA = 0x1AA,
    ID_OBJECT_1AB = 0x1AB,
    ID_OBJECT_1AC = 0x1AC,
    ID_OBJECT_1AD = 0x1AD,
    ID_BEKKAN_1F_DECORATIVE_CHANDELIER = 0x1AE,
    ID_BEKKAN_1F_SQUARE = 0x1AF,
    ID_OBJECT_1B0 = 0x1B0,
    ID_OBJECT_1B1 = 0x1B1,
    ID_OBJECT_1B2 = 0x1B2,
    ID_OBJECT_1B3 = 0x1B3,
    ID_OBJECT_1B4 = 0x1B4,
    ID_MEIRO_TEIEN_OBJ_01B5 = 0x1B5,
    ID_OBJECT_1B6 = 0x1B6,
    ID_OBJECT_1B7 = 0x1B7,
    ID_OBJECT_1B8 = 0x1B8,
    ID_OBJECT_1B9 = 0x1B9,
    ID_OBJECT_1BA = 0x1BA,
    ID_OBJECT_1BB = 0x1BB,
    ID_OBJECT_1BC = 0x1BC,
    ID_OBJECT_1BD = 0x1BD,
    ID_OBJECT_1BE = 0x1BE,
    ID_OBJECT_1BF = 0x1BF,
    ID_OBJECT_1C0 = 0x1C0,
    ID_OBJECT_1C1 = 0x1C1,
    ID_OBJECT_1C2 = 0x1C2,
    ID_OBJECT_1C3 = 0x1C3,
    ID_OBJECT_1C4 = 0x1C4,
    ID_OBJECT_1C5 = 0x1C5,
    ID_OBJECT_1C6 = 0x1C6,
    ID_HONMARU_1F_ELEVATOR_DOOR = 0x1C7,
    ID_HONMARU_1F_BLEEDING_STATUE = 0x1C8,
    ID_HONMARU_1F_ELEVATOR = 0x1C9,
    ID_HONMARU_1F_NITRO_DISPOSAL = 0x1CA,
    ID_HONMARU_1F_BLEEDING_STATUE_BLOOD = 0x1CB,
    ID_HONMARU_1F_BLEEDING_STATUE_BLOOD_SPOT = 0x1CC,
    ID_HONMARU_1F_ELEVATOR_SWITCH_EFFECT_SPAWNER = 0x1CD,
    ID_OBJECT_1CE = 0x1CE,
    ID_OBJECT_1CF = 0x1CF,
    ID_OBJECT_1D0 = 0x1D0,
    ID_OBJECT_1D1 = 0x1D1,
    ID_OBJECT_1D2 = 0x1D2,
    ID_OBJECT_1D3 = 0x1D3,
    ID_OBJECT_1D4 = 0x1D4,
    ID_OBJECT_1D5 = 0x1D5,
    ID_HONMARU_4F_MINAMI_LIBRARY_PIECE = 0x1D6,
    ID_OBJECT_1D7 = 0x1D7,
    ID_OBJECT_1D8 = 0x1D8,
    ID_HONMARU_5F_WOODEN_BRIDGE = 0x1D9,
    ID_HONMARU_5F_ELEVATOR = 0x1DA,
    ID_OBJECT_1DB = 0x1DB,
    ID_OBJECT_1DC = 0x1DC,
    ID_OBJECT_1DD = 0x1DD,
    ID_OBJECT_1DE = 0x1DE,
    ID_OBJECT_1DF = 0x1DF,
    ID_OBJECT_1E0 = 0x1E0,
    ID_OBJECT_1E1 = 0x1E1,
    ID_OBJECT_1E2 = 0x1E2,
    ID_OBJECT_1E3 = 0x1E3,
    ID_OBJECT_1E4 = 0x1E4,
    ID_OBJECT_1E5 = 0x1E5,
    ID_OBJECT_1E6 = 0x1E6,
    ID_OBJECT_1E7 = 0x1E7,
    ID_OBJECT_1E8 = 0x1E8,
    ID_OBJECT_1E9 = 0x1E9,
    ID_OBJECT_1EA = 0x1EA,
    ID_OBJECT_1EB = 0x1EB,
    ID_OBJECT_1EC = 0x1EC,
    ID_OBJECT_1ED = 0x1ED,
    ID_OBJECT_1EE = 0x1EE,
    ID_OBJECT_1EF = 0x1EF,
    ID_OBJECT_1F0 = 0x1F0,
    ID_OBJECT_1F1 = 0x1F1,
    ID_OBJECT_1F2 = 0x1F2,
    ID_OBJECT_1F3 = 0x1F3,
    ID_OBJECT_1F4 = 0x1F4,
    ID_OBJECT_1F5 = 0x1F5,
    ID_OBJECT_1F6 = 0x1F6,
    ID_OBJECT_1F7 = 0x1F7,
    ID_OBJECT_1F8 = 0x1F8,
    ID_OBJECT_1F9 = 0x1F9,
    ID_OBJECT_1FA = 0x1FA,
    ID_OBJECT_1FB = 0x1FB,
    ID_OBJECT_1FC = 0x1FC,
    ID_OBJECT_1FD = 0x1FD,
    ID_OBJECT_1FE = 0x1FE,
    ID_OBJECT_1FF = 0x1FF,
    ID_OBJECT_200 = 0x200,
    ID_OBJECT_201 = 0x201,
    ID_OBJECT_202 = 0x202,
    ID_OBJECT_203 = 0x203,
    ID_OBJECT_204 = 0x204,
    ID_OBJECT_205 = 0x205,
    ID_OBJECT_206 = 0x206,
    ID_OBJECT_207 = 0x207,
    ID_OBJECT_208 = 0x208,
    ID_OBJECT_209 = 0x209,
    ID_OBJECT_20A = 0x20A,
    ID_OBJECT_20B = 0x20B,
    ID_OBJECT_20C = 0x20C,
    ID_OBJECT_20D = 0x20D,
    ID_OBJECT_20E = 0x20E,
    ID_OBJECT_20F = 0x20F,
    ID_OBJECT_210 = 0x210,
    ID_OBJECT_211 = 0x211,
    ID_OBJECT_212 = 0x212,
    ID_OBJECT_213 = 0x213,
    ID_OBJECT_214 = 0x214,
    ID_OBJECT_215 = 0x215,
    ID_OBJECT_216 = 0x216,
    ID_OBJECT_217 = 0x217,
    ID_OBJECT_218 = 0x218,
    ID_OBJECT_219 = 0x219,
    ID_OBJECT_21A = 0x21A,
    ID_OBJECT_21B = 0x21B,
    ID_OBJECT_21C = 0x21C,
    ID_OBJECT_21D = 0x21D,
    ID_OBJECT_21E = 0x21E,
    ID_OBJECT_21F = 0x21F,
    ID_ROSE_VENTILATOR = 0x220,
    ID_ROSE_DOOR = 0x221,
    ID_OBJECT_222 = 0x222,
    ID_OBJECT_223 = 0x223,
    ID_TOU_TURO_DOOR = 0x224,
    ID_OBJECT_225 = 0x225,
    ID_OBJECT_226 = 0x226,
    ID_OBJECT_227 = 0x227,
    ID_OBJECT_228 = 0x228,
    ID_OBJECT_229 = 0x229,
    ID_OBJECT_22A = 0x22A
};
typedef enum ObjectID {
    ENGINE_GAMESTATEMGR = (((OBJ_KIND_NONE) << 8) | (ID_GAMESTATEMGR)),
    ENGINE_OBJ_002 = (((OBJ_KIND_NONE) << 8) | (ID_OBJECT_002)),
    ENGINE_OBJ_003 = (((OBJ_KIND_NONE) << 8) | (ID_OBJECT_003)),
    ENGINE_DMAMGR = (((OBJ_KIND_NONE) << 8) | (ID_DMAMGR)),
    ENGINE_GAMEPLAYMGR = (((OBJ_KIND_NONE) << 8) | (ID_GAMEPLAYMGR)),
    ENGINE_MAP_OBJECT_PARENT = (((OBJ_KIND_NONE) << 8) | (ID_MAP_OBJECT_PARENT)),
    ENGINE_PLAYER_CONTROLLER = (((OBJ_KIND_NONE) << 8) | (ID_PLAYER_CONTROLLER)),
    ENGINE_MASTER_LIGHT_MGR = (((OBJ_KIND_NONE) << 8) | (ID_MASTER_LIGHT_MGR)),
    ENGINE_MAP_SETUP = (((OBJ_KIND_NONE) << 8) | (ID_MAP_SETUP)),
    ENGINE_ENEMY_PARENT = (((OBJ_KIND_NONE) << 8) | (ID_ENEMY_PARENT)),
    ENGINE_GAMENOTE_DELETE_MGR_CREATOR = (((OBJ_KIND_NONE) << 8) | (ID_GAMENOTE_DELETE_MGR_CREATOR)),
    ENGINE_GAMENOTE_DELETE = (((OBJ_KIND_NONE) << 8) | (ID_GAMENOTE_DELETE)),
    ENGINE_GAMENOTE_DELETE_MGR = (((OBJ_KIND_NONE) << 8) | (ID_GAMENOTE_DELETE_MGR)),
    ENGINE_KONAMI_KCEK_LOGOS_CREATOR = (((OBJ_KIND_NONE) << 8) | (ID_KONAMI_KCEK_LOGOS_CREATOR)),
    ENGINE_KONAMI_KCEK_LOGOS = (((OBJ_KIND_NONE) << 8) | (ID_KONAMI_KCEK_LOGOS)),
    ENGINE_TITLE_SCREEN_TEXT_MGR = (((OBJ_KIND_NONE) << 8) | (ID_TITLE_SCREEN_TEXT_MGR)),
    ENGINE_OPENING_CREATOR = (((OBJ_KIND_NONE) << 8) | (ID_OPENING_CREATOR)),
    ENGINE_OPENING = (((OBJ_KIND_NONE) << 8) | (ID_OPENING)),
    ENGINE_TITLE_SCREEN_CREATOR = (((OBJ_KIND_NONE) << 8) | (ID_TITLE_SCREEN_CREATOR)),
    ENGINE_TITLE_SCREEN = (((OBJ_KIND_NONE) << 8) | (ID_TITLE_SCREEN)),
    ENGINE_FILE_SELECT_CREATOR = (((OBJ_KIND_NONE) << 8) | (ID_FILE_SELECT_CREATOR)),
    ENGINE_FILE_SELECT_MGR = (((OBJ_KIND_NONE) << 8) | (ID_FILE_SELECT_MGR)),
    ENGINE_OPTIONS_CREATOR = (((OBJ_KIND_NONE) << 8) | (ID_OPTIONS_CREATOR)),
    ENGINE_OPTIONS = (((OBJ_KIND_NONE) << 8) | (ID_OPTIONS)),
    ENGINE_TITLE_DEMO_CREATOR = (((OBJ_KIND_NONE) << 8) | (ID_TITLE_DEMO_CREATOR)),
    ENGINE_TITLE_DEMO = (((OBJ_KIND_NONE) << 8) | (ID_TITLE_DEMO)),
    ENGINE_CREDITSMGR_CREATOR = (((OBJ_KIND_NONE) << 8) | (ID_CREDITSMGR_CREATOR)),
    ENGINE_CREDITSMGR = (((OBJ_KIND_NONE) << 8) | (ID_CREDITSMGR)),
    ENGINE_OBJ_01C = (((OBJ_KIND_NONE) << 8) | (ID_OBJECT_01C)),
    ENGINE_GAME_OVER_CREATOR = (((OBJ_KIND_NONE) << 8) | (ID_GAME_OVER_CREATOR)),
    ENGINE_GAME_OVER = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_GAME_OVER)),
    CUTSCENE_MANDRAGORA_TEXTBOX = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_MANDRAGORA_TEXTBOX)),
    CUTSCENE_NITRO_TEXTBOX = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_NITRO_TEXTBOX)),
    CUTSCENE_NITRO_DISPOSAL_TEXTBOX = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_NITRO_DISPOSAL_TEXTBOX)),
    CUTSCENE_EXPLOSIVE_WALL_SPOT = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_EXPLOSIVE_WALL_SPOT)),
    CUTSCENE_BOTTOM_ELEVATOR_ACTIVATOR_TEXTBOX = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_BOTTOM_ELEVATOR_ACTIVATOR_TEXTBOX)),
    CUTSCENE_LIBRARY_PUZZLE = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_LIBRARY_PUZZLE)),
    CUTSCENE_INTERACTABLES = (((OBJ_KIND_NONE) << 8) | (ID_INTERACTABLES)),
    CUTSCENE_CUTSCENE_TRIGGER = (((OBJ_KIND_NONE) << 8) | (ID_CUTSCENE_TRIGGER)),
    CUTSCENE_CUTSCENEMGR = (((OBJ_KIND_NONE) << 8) | (ID_CUTSCENEMGR)),
    CUTSCENE_CS_FILM_REEL = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_CS_FILM_REEL)),
    CUTSCENE_CUTSCENE_UNUSED_DEATH = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_CUTSCENE_UNUSED_DEATH)),
    CUTSCENE_CUTSCENE_FOREST_INTRO = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_CUTSCENE_FOREST_INTRO)),
    CUTSCENE_CUTSCENE_CREDITS = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_CUTSCENE_CREDITS)),
    CUTSCENE_DISTORTION = (((OBJ_KIND_NONE) << 8) | (ID_DISTORTION)),
    CAMERA_CAMERAMGR = (((OBJ_KIND_NONE) << 8) | (ID_CAMERAMGR)),
    CAMERA_OBJ_06B = (((OBJ_KIND_NONE) << 8) | (ID_OBJECT_06B)),
    CAMERA_PLAYER_CAMERA_CONTROLLER = (((OBJ_KIND_NONE) << 8) | (ID_PLAYER_CAMERA_CONTROLLER)),
    CAMERA_MASTER_LIGHT_MGR = (((OBJ_KIND_NONE) << 8) | (ID_MASTER_LIGHT_MGR)),
    CAMERA_MODEL_LIGHTING = (((OBJ_KIND_NONE) << 8) | (ID_MODEL_LIGHTING)),
    CAMERA_POINT_LIGHT = (((OBJ_KIND_NONE) << 8) | (ID_POINT_LIGHT)),
    PLAYER_REINHARDT = (((OBJ_KIND_NONE) << 8) | (ID_REINHARDT)),
    PLAYER_REINHARDT_ALT = (((OBJ_KIND_NONE) << 8) | (ID_REINHARDT_ALT)),
    PLAYER_REINHARDT_ATTACKMGR = (((OBJ_KIND_NONE) << 8) | (ID_REINHARDT_ATTACKMGR)),
    PLAYER_REINHARDT_DYNAMIC_SCARF = (((OBJ_KIND_NONE) << 8) | (ID_REINHARDT_DYNAMIC_SCARF)),
    PLAYER_CARRIE = (((OBJ_KIND_NONE) << 8) | (ID_CARRIE)),
    PLAYER_CARRIE_ALT = (((OBJ_KIND_NONE) << 8) | (ID_CARRIE_ALT)),
    PLAYER_CARRIE_ATTACKMGR = (((OBJ_KIND_NONE) << 8) | (ID_CARRIE_ATTACKMGR)),
    PLAYER_CARRIE_DYNAMIC_SKIRT = (((OBJ_KIND_NONE) << 8) | (ID_CARRIE_DYNAMIC_SKIRT)),
    PLAYER_CARRIE_DYNAMIC_RIGHT_STRIP = (((OBJ_KIND_NONE) << 8) | (ID_CARRIE_DYNAMIC_RIGHT_STRIP)),
    PLAYER_CARRIE_DYNAMIC_LEFT_STRIP = (((OBJ_KIND_NONE) << 8) | (ID_CARRIE_DYNAMIC_LEFT_STRIP)),
    PLAYER_ENEMY_TARGET_GFX = (((OBJ_KIND_NONE) << 8) | (ID_ENEMY_TARGET_GFX)),
    ENEMY_GARDENER = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_GARDENER)),
    ENEMY_DEATH = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_DEATH)),
    ENEMY_DEMON_DRACULA_ASSETS_LOADER = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_DEMON_DRACULA_ASSETS_LOADER)),
    ENEMY_MUD_MAN_ASSETS_LOADER = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_MUD_MAN_ASSETS_LOADER)),
    ENEMY_BLOOD_MAN_ASSETS_LOADER = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_BLOOD_MAN_ASSETS_LOADER)),
    ENEMY_ICE_MAN_ASSETS_LOADER = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_ICE_MAN_ASSETS_LOADER)),
    ENEMY_OPENING_BAT = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_OPENING_BAT)),
    EFFECT_EFFECTMGR = (((OBJ_KIND_NONE) << 8) | (ID_EFFECTMGR)),
    EFFECT_FIRE = (((OBJ_KIND_NONE) << 8) | (ID_FIRE)),
    EFFECT_FIRE_SPARKLES = (((OBJ_KIND_NONE) << 8) | (ID_FIRE_SPARKLES)),
    EFFECT_PICKABLE_ITEM_FLASH = (((OBJ_KIND_NONE) << 8) | (ID_PICKABLE_ITEM_FLASH)),
    MENU_GAMEPLAY_MENUMGR = (((OBJ_KIND_NONE) << 8) | (ID_GAMEPLAY_MENUMGR)),
    MENU_MFDS = (((OBJ_KIND_NONE) << 8) | (ID_MFDS)),
    MENU_LENS = (((OBJ_KIND_NONE) << 8) | (ID_LENS)),
    MENU_HUD = (((OBJ_KIND_NONE) << 8) | (ID_HUD)),
    MENU_RENON_SHOP = (((OBJ_KIND_NONE) << 8) | (ID_RENON_SHOP)),
    MENU_OPTIONS_CONTROLLER = (((OBJ_KIND_NONE) << 8) | (ID_OPTIONS_CONTROLLER)),
    MENU_FILE_SELECT_CONTROLLER = (((OBJ_KIND_NONE) << 8) | (ID_FILE_SELECT_CONTROLLER)),
    MENU_CHARACTER_SELECT = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_CHARACTER_SELECT)),
    MENU_NECRONOMICON = (((OBJ_KIND_NONE) << 8) | (ID_NECRONOMICON)),
    MENU_PAGE = (((OBJ_KIND_NONE) << 8) | (ID_PAGE)),
    MENU_SCROLL = (((OBJ_KIND_NONE) << 8) | (ID_SCROLL)),
    MENU_MARK = (((OBJ_KIND_NONE) << 8) | (ID_MARK)),
    MENU_PAUSE = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_PAUSE)),
    MENU_SAVEGAME = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_SAVEGAME)),
    MENU_TEXTBOX_ADVANCE_ARROW = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_TEXTBOX_ADVANCE_ARROW)),
    MENU_ENTRANCE_MAP_NAME_DISPLAY = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_ENTRANCE_MAP_NAME_DISPLAY)),
    MENU_CONTRACTMGR = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_CONTRACTMGR)),
    MENU_RENON_BRIEFCASE = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_RENON_BRIEFCASE)),
    MENU_MINI_SCROLL = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_MINI_SCROLL)),
    MENU_OBJ_13F = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_OBJECT_13F)),
    MENU_EASY_ENDING = (((OBJ_KIND_MAP_OVERLAY) << 8) | (ID_EASY_ENDING)),
    MENU_STAGE_SELECT = (((OBJ_KIND_NONE) << 8) | (ID_STAGE_SELECT)),
    MAP_HANDLING_LOADING_ZONE = (((OBJ_KIND_NONE) << 8) | (ID_LOADING_ZONE)),
    STAGE_OBJECT_LEVER = (((OBJ_KIND_NONE) << 8) | (ID_LEVER)),
    STAGE_OBJECT_OBJ_0172 = (((OBJ_KIND_NONE) << 8) | (ID_OBJECT_172)),
    STAGE_OBJECT_OBJ_017C = (((OBJ_KIND_NONE) << 8) | (ID_OBJECT_17C)),
    STAGE_COMMON_MOON = (((OBJ_KIND_NONE) << 8) | (ID_COMMON_MOON)),
    STAGE_OBJECT_BEKKAN_1F_DECORATIVE_CHANDELIER = (((OBJ_KIND_NONE) << 8) | (ID_BEKKAN_1F_DECORATIVE_CHANDELIER)),
    STAGE_OBJECT_BEKKAN_1F_SQUARE = (((OBJ_KIND_NONE) << 8) | (ID_BEKKAN_1F_SQUARE)),
    STAGE_OBJECT_MEIRO_TEIEN_OBJ_01B5 = (((OBJ_KIND_NONE) << 8) | (ID_MEIRO_TEIEN_OBJ_01B5)),
    STAGE_OBJECT_HONMARU_1F_ELEVATOR_DOOR = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_1F_ELEVATOR_DOOR)),
    STAGE_OBJECT_HONMARU_1F_BLEEDING_STATUE = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_1F_BLEEDING_STATUE)),
    STAGE_OBJECT_HONMARU_1F_ELEVATOR = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_1F_ELEVATOR)),
    STAGE_OBJECT_HONMARU_1F_NITRO_DISPOSAL = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_1F_NITRO_DISPOSAL)),
    STAGE_OBJECT_HONMARU_1F_BLEEDING_STATUE_BLOOD = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_1F_BLEEDING_STATUE_BLOOD)),
    STAGE_OBJECT_HONMARU_1F_BLEEDING_STATUE_BLOOD_SPOT = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_1F_BLEEDING_STATUE_BLOOD_SPOT)),
    STAGE_OBJECT_HONMARU_1F_ELEVATOR_SWITCH_EFFECT_SPAWNER = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_1F_ELEVATOR_SWITCH_EFFECT_SPAWNER)),
    STAGE_OBJECT_HONMARU_4F_MINAMI_LIBRARY_PIECE = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_4F_MINAMI_LIBRARY_PIECE)),
    STAGE_OBJECT_HONMARU_5F_WOODEN_BRIDGE = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_5F_WOODEN_BRIDGE)),
    STAGE_OBJECT_HONMARU_5F_ELEVATOR = (((OBJ_KIND_NONE) << 8) | (ID_HONMARU_5F_ELEVATOR)),
    STAGE_OBJECT_ROSE_VENTILATOR = (((OBJ_KIND_NONE) << 8) | (ID_ROSE_VENTILATOR)),
    STAGE_OBJECT_ROSE_DOOR = (((OBJ_KIND_ENABLE_COLLISION) << 8) | (ID_ROSE_DOOR)),
    STAGE_OBJECT_TOU_TURO_DOOR = (((OBJ_KIND_ENABLE_COLLISION) << 8) | (ID_TOU_TURO_DOOR))
} ObjectID;

typedef enum ObjectExecFlag {
    OBJ_EXEC_FLAG_DONT_DESTROY = 0x0010,
    OBJ_EXEC_FLAG_PAUSE = 0x4000,
    OBJ_EXEC_FLAG_TOP = 0x8000
} ObjectExecFlag;
typedef void (*ObjectFunc)(void* self);
typedef void (*ObjectDestroyFunc)(void* self);
typedef union ObjectFuncInfo {
    struct {
        u8 timer;
        u8 function;
    };
    u16 whole;
} ObjectFuncInfo;
typedef struct ObjectHeader {
    s16 ID;
    u16 flags;
    u16 timer;
    s16 field_0x06;
    ObjectFuncInfo current_function[3];
    s16 function_info_ID;
    ObjectDestroyFunc destroy;
    struct ObjectHeader* parent;
    struct ObjectHeader* next;
    struct ObjectHeader* child;
} ObjectHeader;
typedef struct Object {
    ObjectHeader header;
    u16 alloc_data_entries;
    u16 graphic_container_entries;
    Figure* figures[4];
    void* alloc_data[16];
} Object;
typedef struct ObjectFileInfo {
    union {
        u32 addr;
        u32 file_ID;
    };
    u32 file_padding;
} ObjectFileInfo;
int object_isValid(ObjectHeader* self);
void object_free(Object* self);
void clearAllObjects(void);
ObjectHeader* object_allocate(ObjectID ID);
void updateObjectListFreeSlot(void);
ObjectHeader* object_create(ObjectHeader* parent, ObjectID ID);
ObjectHeader* object_createAndSetChild(ObjectHeader* parent, ObjectID ID);
Object* object_findFirstObjectByID(ObjectID ID, Object* current_object);
Object* objectList_findFirstObjectByID(ObjectID ID);
Object* object_findObjectBetweenIDRange(ObjectID min_ID, ObjectID max_ID, Object* current_object);
Object* objectList_findObjectBetweenRange(ObjectID min_ID, ObjectID max_ID);
Object* object_findObjectByIDAndType(ObjectID ID, Object* current_object);
Object* objectList_findObjectByIDAndType(ObjectID ID);
Object* func_8000211C_2D1C(s32 ID);
void* object_allocEntryInList(Object* self, HeapKind heap_kind, u32 size, s32 alloc_data_index);
void* object_allocEntryInListAndClear(
    Object* self, HeapKind heap_kind, u32 size, s32 alloc_data_index
);
void* object_allocGraphicContainerEntryInList(
    Object* self, u32 size, HeapKind heap_kind, s32 alloc_data_index
);
void object_freeData(Object* self, s32 alloc_data_index);
void object_executeChildObject(ObjectHeader* self);
void object_execute(ObjectHeader* self);
void func_800026D8_32D8(ObjectHeader* self);
void object_destroyChildrenAndModelInfo(ObjectHeader* self);
void object_curLevel_goToFunc(
    ObjectFuncInfo current_functionInfo[], s16* function_info_ID, s32 function
);
void object_curLevel_goToNextFunc(ObjectFuncInfo current_functionInfo[], s16* function_info_ID);
void object_prevLevel_goToNextFunc(ObjectFuncInfo current_functionInfo[], s16* function_info_ID);
void object_nextLevel_goToNextFunc(ObjectFuncInfo current_functionInfo[], s16* function_info_ID);
void object_curLevel_goToNextFuncAndClearTimer(
    ObjectFuncInfo current_functionInfo[], s16* function_info_ID
);
void object_curLevel_goToPrevFunc(ObjectFuncInfo current_functionInfo[], s16* function_info_ID);
void object_prevLevel_goToPrevFunc(ObjectFuncInfo current_functionInfo[], s16* function_info_ID);
void object_nextLevel_goToPrevFunc(ObjectFuncInfo current_functionInfo[], s16* function_info_ID);
void object_curLevel_goToPrevFuncAndClearTimer(
    ObjectFuncInfo current_functionInfo[], s16* function_info_ID
);
void object_curLevel_goToFunc(
    ObjectFuncInfo current_functionInfo[], s16* function_info_ID, s32 function
);
void object_curLevel_goToFuncInLevel(
    ObjectFuncInfo current_functionInfo[], s16* function_info_ID, s16 level, s32 function
);
void object_prevLevel_goToFunc(
    ObjectFuncInfo current_functionInfo[], s16* function_info_ID, s32 function
);
void object_nextLevel_goToFunc(
    ObjectFuncInfo current_functionInfo[], s16* function_info_ID, s32 function
);
void object_doNothing(Object* self);
void object_goToNextFuncNoCondition(Object* self);
void object_goToNextFuncIfTimerIsTwo(Object* self);
void object_goToNextFuncIfTimerIsThree(Object* self);
void object_fadeOutNineFramesAndGoToNextFunc(Object* self);
void object_fadeOutFifteenFramesAndGoToNextFunc(Object* self);
void object_fadeOutTwentyOneFramesAndGoToNextFunc(Object* self);
void object_fadeOutThirtyFramesAndGoToNextFunc(Object* self);
void object_fadeOutFortyFiveFramesAndGoToNextFunc(Object* self);
void object_fadeOutSixtyFramesAndGoToNextFunc(Object* self);
void object_goToNextFuncIfNotFading(Object* self);
void func_80002570_3170(ObjectHeader* self);
Object* func_80001BE4_27E4(ObjectID object_ID, Object* arg1);
extern void mapOverlay(ObjectHeader* self);
extern void unmapOverlay();
void* allocStructInObjectEntryList(
    const char* name, Object* object, u32 size, s32 alloc_data_index
);
GraphicContainerHeader* allocGraphicContainerInObjectEntryList(
    const char* name, Object* object, u32 size, s32 alloc_data_index
);
extern Object objects_array[384];
extern u16 objects_number_of_instances_per_object[554];
extern ObjectFileInfo* objects_file_info[554];
extern ObjectFunc Objects_functions[554];
extern Object* object_list_free_slot;
extern Object* ptr_gameplayParentObject;

typedef struct {
    s16 screen_width;
    s16 screen_height;
    s16 field2_0x4;
    s16 field3_0x6;
    s16 screen_offset_X;
    s16 screen_offset_Y;
    s16 field6_0xc;
    s16 field7_0xe;
    s16 field8_0x10;
    s16 field9_0x12;
    s16 field10_0x14;
    s16 field11_0x16;
    s16 field12_0x18;
    s16 field13_0x1a;
    s16 field14_0x1c;
    s16 field15_0x1e;
} screen_params;
typedef struct {
    f32 fovy;
    f32 aspect;
    f32 near;
    f32 far;
    f32 scale;
} projection_matrix_params;
typedef struct {
    f32 l;
    f32 r;
    f32 b;
    f32 t;
    f32 n;
    f32 f;
    f32 scale;
} projection_matrix_params_ORTHO;
typedef union {
    projection_matrix_params* perspective;
    projection_matrix_params_ORTHO* ortho;
} union_projection_matrix;
typedef struct Camera {
    s16 type;
    u16 flags;
    struct Camera* prev;
    struct Camera* sibling;
    struct Camera* next;
    struct Camera* parent;
    u8 field1_0x14;
    u8 field2_0x15;
    u8 field3_0x16;
    u8 field4_0x17;
    u8 field5_0x18;
    u8 field6_0x19;
    u8 field7_0x1a;
    u8 field8_0x1b;
    u8 field9_0x1c;
    u8 field10_0x1d;
    u8 field11_0x1e;
    u8 field12_0x1f;
    u8 field13_0x20;
    u8 field14_0x21;
    u8 field15_0x22;
    u8 field16_0x23;
    u16 perspNorm;
    u8 field18_0x26;
    u8 field19_0x27;
    u8 field20_0x28;
    u8 field21_0x29;
    u8 field22_0x2a;
    u8 field23_0x2b;
    u8 field24_0x2c;
    u8 field25_0x2d;
    u8 field26_0x2e;
    u8 field27_0x2f;
    screen_params* screen_params;
    union_projection_matrix projection_matrix_params;
    u8 field30_0x38;
    u8 field31_0x39;
    u8 field32_0x3a;
    u8 field33_0x3b;
    Gfx* clip_ratio_dl;
    Vec3f position;
    Vec3 field36_0x4c;
    Angle angle;
    Vec3f look_at_direction;
    u8 field39_0x64;
    u8 field40_0x65;
    u8 field41_0x66;
    u8 field42_0x67;
    Mat4f matrix;
} Camera;
extern Camera* common_camera_8009B430;
extern Camera* common_camera_8009B434;
extern Camera* common_camera_game_view;
extern Camera* common_camera_effects;
extern Camera* common_camera_8009B440;
extern Camera* common_camera_8009B444;
extern Camera* common_camera_8009B448;
extern Camera* common_camera_8009B44C;
extern Camera* common_camera_HUD;
extern Camera* Camera_Create(u16 type, s32 index);
extern void Camera_SetParams(Camera* self, s32 index);
struct Model;
struct MfdsState;
typedef enum MiniScrollFlag {
    MINISCROLL_FLAG_DESTROY_IF_CLOSED = (1 << (24)),
    MINISCROLL_FLAG_SCROLLING_UPWARDS = (1 << (24)),
    MINISCROLL_FLAG_END_SCROLLING = (1 << (25)),
    MINISCROLL_FLAG_CLOSED = (1 << (26)),
    MINISCROLL_FLAG_OPENED = (1 << (27))
} MiniScrollFlag;
typedef enum MiniScrollState {
    MINISCROLL_STATE_OPEN = 1,
    MINISCROLL_STATE_CLOSE = 2,
    MINISCROLL_STATE_SCROLL_UPWARDS = 3,
    MINISCROLL_STATE_SCROLL_DOWNWARDS = 4,
    MINISCROLL_STATE_DESTROY = 5
} MiniScrollState;
typedef struct MiniScrollInner {
    u32 flags;
    s32 scrolling_timer;
    s32 scroll_offset;
    s32 scrolling_speed;
    Vec3f position;
    f32 open_max_height;
    Vec2f width;
    f32 scroll_opened_bottom_limit;
    s32 field_0x2C;
    s32 field_0x30;
    s32 field_0x34;
    Camera* display_camera;
} MiniScrollInner;
typedef struct MiniScrollVertexBuffer {
    GraphicContainerHeader header;
    Vtx vertices[2][230];
} MiniScrollVertexBuffer;
typedef struct MiniScroll {
    ObjectHeader header;
    u8 field_0x20[4];
    struct Model* model;
    struct Model* field_0x28;
    u8 field_0x2C[8];
    MiniScrollVertexBuffer* vtx_buffer;
    MiniScrollInner inner;
} MiniScroll;
typedef struct MiniScrollParameters {
    s32 state;
    s32 after_quit_state;
    u32 scroll_init_delay_timer;
    MiniScroll* scroll;
    struct MfdsState* textbox;
    u8 field_0x14[44];
} MiniScrollParameters;
MiniScroll* MiniScroll_create(void* parent, Camera* camera, s32 param_3, s32 param_4);
u32 MiniScroll_checkFlags(MiniScroll* self, u32 flags);
void MiniScroll_editFlags(MiniScroll* self, u32 flags, s32 setFlags);
struct Model* MiniScroll_getModel(MiniScroll* self);
void MiniScroll_setState(MiniScroll* self, u32 state);
void MiniScroll_setScrollingParams(MiniScroll* self, f32 open_max_height, s32 scrolling_speed);
void MiniScroll_setPosition(MiniScroll* self, f32 X, f32 Y, f32 Z);
void MiniScroll_setWidth(MiniScroll* self, f32 X, f32 Y, f32 scroll_opened_bottom_limit);
extern void MiniScroll_entrypoint(MiniScroll* self);
extern void MiniScroll_init(MiniScroll* self);
extern void MiniScroll_loop(MiniScroll* self);
extern void MiniScroll_open(MiniScroll* self);
extern void MiniScroll_close(MiniScroll* self);
extern void MiniScroll_scrollUpwards(MiniScroll* self);
extern void MiniScroll_scrollDownwards(MiniScroll* self);
extern void MiniScroll_destroy(MiniScroll* self);
extern u32
MiniScroll_renderScroll(MiniScroll* self, s32 scroll_offset, s32 scroll_vertical_position);
extern void MiniScroll_animateOpen(MiniScroll* self);
extern void MiniScroll_animateClose(MiniScroll* self);
extern void MiniScroll_animateScrolling(MiniScroll* self);
extern void func_0F0011F8(MiniScroll* self);
extern void func_0F001248(MiniScroll* self);
extern void func_0F001250(MiniScroll* self);
extern void func_0F001258(MiniScroll* self);
typedef void (*MiniScrollFunc)(MiniScroll*);
typedef struct Model {
    s16 type;
    u16 flags;
    struct Model* prev;
    struct Model* sibling;
    struct Model* next;
    struct Model* parent;
    RGBA primitive_color;
    RGBA environment_color;
    RGBA blend_color;
    RGBA fog_color;
    u16 texture;
    u16 palette;
    u8 field24_0x28;
    u8 field25_0x29;
    u8 field26_0x2a;
    u8 field27_0x2b;
    u8 field28_0x2c;
    u8 field29_0x2d;
    u8 field30_0x2e;
    u8 field31_0x2f;
    u32 material_dlist;
    u32 dlist;
    u32 field34_0x38;
    NIFileID assets_file;
    Vec3f position;
    Angle angle;
    Angle field41_0x52;
    Vec3f size;
    MapActorModel* map_actor_model;
    union {
        Mat4f matrix;
        MiniScrollParameters mini_scroll_params;
    };
} Model;
typedef struct actorPositionalData {
    Vec3f position;
    Angle angle;
} actorPositionalData;
extern void Model_setPosVec3s(Model* self, Vec3* position);
extern void Model_copyPositionalData(Model*, actorPositionalData*);
extern void Model_copyPosToVec3f(Model*, Vec3f*);
extern void Model_setMapActorModelNoCollision(Model*, u32*);
extern Model* Model_createAndSetChild(u32 type, void* parent);
extern Model* Model_createNextNode(u32 parent_type, void* parent);
extern Model* Model_buildHierarchy(u32 type, Model* self, Hierarchy* mdl_hierarchy);




typedef struct {
    u8 field_0x00[sizeof(Object)];
} obj_distortion;


typedef struct {
    f32 field_0x00;
    f32 field_0x04;
    u8 field_0x08;
    u8 field_0x09;
    u8 field_0x0A[4];
    u16 field_0x0E;
    u8 field_0x10[4];
    u32 field_0x14;
} struct_78;
typedef enum WindowFlag {
    WINDOW_FLAG_OPEN_RIGHT = (1 << (0)),
    WINDOW_FLAG_OPEN_LEFT = (1 << (1)),
    WINDOW_FLAG_OPEN_DOWN = (1 << (2)),
    WINDOW_FLAG_OPEN_UP = (1 << (3)),
    WINDOW_FLAG_OPEN_RIGHT_DOWN = (1 << (4)),
    WINDOW_FLAG_OPEN_DOWN_RIGHT = (1 << (5)),
    WINDOW_FLAG_40 = (1 << (6)),
    WINDOW_FLAG_80 = (1 << (7)),
    WINDOW_CLOSING = (1 << (8)),
    WINDOW_OPENING = (1 << (9)),
    WINDOW_OPENED_X = (1 << (12)),
    WINDOW_OPENED_Y = (1 << (13)),
    WINDOW_FLAG_4000 = (1 << (14)),
    WINDOW_FLAG_8000 = (1 << (15)),
    WINDOW_FLAG_40000 = (1 << (18)),
    WINDOW_HIDE = (1 << (19)),
    WINDOW_FLAG_200000 = (1 << (21)),
    WINDOW_FLAG_400000 = (1 << (22)),
    WINDOW_FLAG_ENABLE_DISTORTION_EFFECT = (1 << (23))
} WindowFlag;
typedef struct WindowWork {
    u32 flags;
    Camera* display_camera;
    Vec3f position;
    f32 width;
    f32 height;
    f32 field_0x1C;
    f32 field_0x20;
    f32 window_closing_speed;
    u8 field_0x28[8];
    RGBA primitive_color;
    Vec3f size;
    struct_78* field_0x40;
} WindowWork;
extern void WindowWork_setParams(
    WindowWork* work,
    u32 flags,
    u8 param_3,
    u8 param_4,
    f32 distortion_size,
    f32 param_6,
    void* param_7
);
typedef struct ObjLens {
    ObjectHeader header;
    u8 field_0x20[4];
    struct Model* model;
    struct Model* lower_left_corner;
    struct Model* upper_right_corner;
    struct Model* lower_right_corner;
    struct Model* upper_stripe;
    struct Model* left_stripe;
    struct Model* right_stripe;
    struct Model* lower_stripe;
    struct Model* lens_flash;
    struct Model* lens_background;
    struct Model* lens_background_overlay;
    void* field_0x50;
    void* field_0x54;
    void* field_0x58;
    void* field_0x5C;
    obj_distortion* distortion;
    struct_78* field_0x64;
    WindowWork* field_0x68;
    WindowWork* field_0x6C;
    WindowWork* main_window;
} ObjLens;
extern WindowWork* lens_create(
    void* parent,
    Camera* display_camera,
    u32 flags,
    f32 pos_X,
    f32 pos_Y,
    f32 pos_Z,
    f32 height,
    f32 width,
    f32 closing_speed
);


typedef struct {
    u8 field_0x00[0x78];
} struct_48;
typedef struct {
    RGBA color;
    s8 direction[3];
    u8 index;
} light_parameters;
typedef struct FigureLight {
    s16 type;
    u16 flags;
    struct FigureLight* prev;
    struct FigureLight* sibling;
    struct FigureLight* next;
    struct FigureLight* parent;
    u8 field1_0x14[28];
    struct FigureLight* field2_0x30;
    struct_48* field3_0x34;
    u8 field4_0x38[4];
    s32 number_of_lights;
    u8 field6_0x40[40];
    RGBA ambient_color;
    u8 field_0x6C[3];
    u8 field_0x6F;
    light_parameters lights[7];
} FigureLight;
extern FigureLight* light_create(u16 type);
extern FigureLight* map_lights[3];
extern FigureLight* ptr_master_light;
extern void light_setAmbientColor(FigureLight* self, u32 ambient_color);
extern void light_setColorAndDirection(FigureLight* self, s32 index, u32 color, u32 direction);
extern s32 light_addColorAndDirection(FigureLight* self, u32 color, u32 direction);
extern s32 light_addColorAndDirectionOrSetAmbientColorIfListIsEmpty(
    FigureLight* self, u32 ambient_color, u32 direction
);
typedef struct {
    ObjectHeader header;
    u8 field_0x20[4];
    struct Model* model;
    FigureLight* arrow_light;
    u8 field_0x2C[12];
    s32 fade_timer;
    u8 field_0x3C[28];
    s32 disable_arrow;
    u8 field_0x5C[24];
} TextboxAdvanceArrow;
void TextboxAdvanceArrow_entrypoint(TextboxAdvanceArrow* self);
void TextboxAdvanceArrow_init(TextboxAdvanceArrow* self);
void TextboxAdvanceArrow_loop(TextboxAdvanceArrow* self);
void TextboxAdvanceArrow_destroy(TextboxAdvanceArrow* self);
typedef void (*TextboxAdvanceArrowFunc)(TextboxAdvanceArrow*);
extern const u32 TEXTBOX_ADVANCE_ARROW_DL;
typedef enum MfdsStateFlag {
    MFDS_FLAG_MENU_TEXT_ID_PRINTS_ITEM = (1 << (0)),
    MFDS_FLAG_MENU_TEXT_ID_PRINTS_MENU_STRING = (1 << (1)),
    MFDS_FLAG_KEEP_SHOWING_LINE = (1 << (2)),
    MFDS_FLAG_00000008 = (1 << (3)),
    MFDS_FLAG_PRINT_NUMBER = (1 << (4)),
    MFDS_FLAG_OPTION_SELECTION = (1 << (5)),
    MFDS_FLAG_DISPLAY_LENS = (1 << (6)),
    MFDS_FLAG_ALLOC_TEXTBOX_IN_MENU_DATA_HEAP = (1 << (14)),
    MFDS_FLAG_8000 = (1 << (15)),
    MFDS_FLAG_GAMEPLAYMENUMGR_TEXTBOX = (1 << (16)),
    MFDS_FLAG_LEAVE_SPACE_FOR_SELECTION_ARROW = (1 << (17)),
    MFDS_FLAG_ALLOW_TRANSPARENCY_CHANGE = (1 << (18)),
    MFDS_FLAG_UPDATE_SCALE = (1 << (19)),
    MFDS_FLAG_SLOW_TEXT_SPEED = (1 << (20)),
    MFDS_FLAG_ALLOW_VARIABLE_SPEED = (1 << (21)),
    MFDS_FLAG_FAST_TEXT_SPEED = (1 << (22)),
    MFDS_FLAG_AUTO_SKIP_TEXT = (1 << (23)),
    MFDS_FLAG_UPDATE_STRING = (1 << (24)),
    MFDS_FLAG_2000000 = (1 << (25)),
    MFDS_FLAG_CLOSE_TEXTBOX = (1 << (26)),
    MFDS_FLAG_OPEN_TEXTBOX = (1 << (27)),
    MFDS_FLAG_CLOSE_LENS = (1 << (28)),
    MFDS_FLAG_OPEN_LENS = (1 << (29)),
    MFDS_FLAG_TEXT_IS_PARSED = (1 << (30)),
    MFDS_FLAG_HIDE_TEXTBOX = (1 << (31))
} MfdsStateFlag;
typedef enum MfdsWorkFlag {
    MFDS_WORK_FLAG_TEXT_SHOULD_SCROLL = (1 << (0))
} MfdsWorkFlag;
typedef enum MfdsStateNumberVisualFlag {
    NUMBER_VISUAL_FLAG_PRINT_IN_HEX = (1 << (0)),
    NUMBER_VISUAL_FLAG_PRINT_PLUS_SYMBOL_FOR_POSITIVE_NUMBERS = (1 << (1)),
    NUMBER_VISUAL_FLAG_ADD_LEADING_ZEROES = (1 << (2)),
    NUMBER_VISUAL_FLAG_ADD_NEW_LINE = (1 << (3)),
    NUMBER_VISUAL_FLAG_USE_GOLD_JEWEL_FONT = (1 << (4)),
    NUMBER_VISUAL_FLAG_ADD_G_AFTER_NUMBER = (1 << (5))
} MfdsStateNumberVisualFlag;
typedef enum MfdsWorkArrowState {
    NOT_DISPLAYING_TEXTBOX_ARROW = 0,
    DISPLAYING_TEXTBOX_ARROW = 1,
    TEXTBOX_ARROW_AUTO_ADVANCING = 2
} MfdsWorkArrowState;
typedef struct MfdsColorAnimData {
    u16 color;
    u16 time;
} MfdsColorAnimData;
typedef struct MfdsColorAnimationState {
    u8 field_0x00;
    u8 transition_time[4];
    u8 field_0x05[4];
    u8 transition_point[4];
    u8 field_0x0D[3];
    MfdsColorAnimData* color_anim_data[4];
    u8 max_transition_time[4];
} MfdsColorAnimationState;
typedef struct MfdsWork {
    u16* parsed_text_ptr;
    s8 text_speed;
    u8 field_0x05;
    s16 indentation;
    s16 Y_and_X_pos_offsets;
    u8 scroll_timer;
    u8 palette;
    s8 current_tex_buffer_entry;
    s8 textbox_advance_arrow_state;
    s16 time_until_auto_advance_textbox;
    u8 flags;
    u8 field_0x11;
    Vec2 current_position;
    Vec2 initial_position;
    u8 left_margin;
    u8 num_options;
    u8 current_option;
    u8 field_0x1D;
    u8 option_selection_IDs[6];
    u8 field_0x24[10];
    u8 display_time;
    u8 field_0x2F;
    MfdsColorAnimationState* color_anim_state;
} MfdsWork;
typedef struct MfdsTexBufferEntry {
    u8 field_0x00;
    u8 field_0x01;
    u16 text_char;
    s16 field_0x04;
    u8 field_0x06;
    u8 field_0x07;
    u8 field_0x08;
    u8 char_tex_buffer[128];
    u8 field_0x89;
} MfdsTexBufferEntry;
typedef struct MfdsTexBuffer {
    MfdsTexBufferEntry entries[5];
} MfdsTexBuffer;
typedef struct MfdsLtexBufferEntry {
    u16 text_char;
    u16 field_0x02;
    u8 field_0x04;
    u16 char_texture_raw_data[49];
    u8 field_0x67;
} MfdsLtexBufferEntry;
typedef struct MfdsLtexBuffer {
    MfdsLtexBufferEntry entries[5];
} MfdsLtexBuffer;
typedef struct MfdsDlSize {
    u32 dlist_buffer_size;
    u32 dlist_graphic_buffer_start_offset;
    u32 vertices_graphic_buffer_start_offset;
} MfdsDlSize;
typedef struct MfdsNumberWork {
    u16 text_buffer[13];
} MfdsNumberWork;
typedef union MfdsStateMiscTextIds {
    u8 menu_text_ID;
    u8 item_ID;
} MfdsStateMiscTextIds;
typedef struct MfdsHeightWidthParams {
    s8 height;
    s8 width;
} MfdsHeightWidthParams;
typedef struct MfdsState {
    u32 flags;
    Camera* display_camera;
    u16* text;
    u16* item_amount_text;
    MfdsWork* mfds_work;
    Vec2 position;
    f32 position_Z;
    Vec2f scale;
    s32 number;
    s32 previous_number;
    u16 width;
    u8 previous_textbox_option;
    u8 textbox_option;
    u8 line;
    u8 field_0x31;
    u8 character_spacing;
    u8 left_margin;
    u8 palette;
    MfdsStateMiscTextIds misc_text_IDs[5];
    u8 number_visual_flags;
    u8 display_time;
    MfdsHeightWidthParams height_and_width_per_line[11];
    u8 field_0x52;
    u8 field_0x53;
    u32 window_flags;
    f32 window_closing_speed;
    ObjLens* lens;
} MfdsState;
typedef struct ObjMfds {
    ObjectHeader header;
    u16 field_0x20;
    u16 field_0x22;
    u8 field_0x24[4];
    struct Model* model;
    u8 field_0x2C[8];
    GraphicContainerHeader* mfds_double;
    void* field_0x38;
    void* field_0x3C;
    struct TextboxAdvanceArrow* advance_arrow;
    void* field_0x44;
    void* field_0x48;
    void* field_0x4C;
    union {
        u16* mfds_menu_string;
        u16* mfds_item_form;
    };
    MfdsNumberWork* number;
    MfdsColorAnimationState* color_anim_state;
    WindowWork* window;
    MfdsDlSize* dl_size;
    MfdsLtexBuffer* ltex_buffer;
    MfdsTexBuffer* tex_buffer;
    MfdsWork* work;
    MfdsState* state;
} ObjMfds;
extern MfdsState* textbox_create(ObjectHeader* parent_object, Camera* display_camera, u32 flags);
extern void
textbox_setDimensions(MfdsState* self, u8 line, u16 width, u8 param_4, u8 character_spacing);
extern void textbox_setPos(MfdsState* self, u16 x, u16 y, s32);
extern void
textbox_setMessagePtr(MfdsState* self, u16* text, u16* item_amount_number_text, s16 number);
extern void textbox_enableLens(MfdsState* self, u32 window_work_flags, f32 window_closing_speed);
extern u16* text_getMessageFromPool(u16* message_pool_base_ptr, s32 id);
extern void textbox_setScaleParameters(
    MfdsState* self,
    u8 number_of_vertical_vertices,
    u8 number_of_horizontal_vertices,
    f32 position_Z,
    f32 scale_X,
    f32 scale_Y,
    u8 allow_transparency_change,
    u8 leave_space_for_selection_arrow
);
extern void
text_convertSignedIntegerToText(u32 number, u16* dest, u8 number_of_chars, u32 number_visual_flags);
extern u16* text_findCharInString(u16* text, u16 char_to_find);
extern u16* convertUTF16ToCustomTextFormat(u16* text_buffer);
extern void textbox_setHeightAndWidth(MfdsState* self, u32 index, u8 text_height, u8 text_width);
extern MfdsState* GameplayCommonTextbox_getMapMessage(u16 text_ID, u8 textbox_display_time);
extern MfdsColorAnimData text_color_anim_data_table[4][8];

typedef struct HUDParams {
    u8 flags;
    u8 field_0x01;
    s16 damage_received;
    f32 health_bar_damage_length;
    u8 field_0x08;
    u8 field_0x09;
    s16 life_lost_before_entering_loading_zone;
    f32 amount_of_life_lost;
    s16 hour_marker_angle;
    s16 minute_marker_angle;
    u8 clockDayNightGraphic_timeOfDay;
    u8 boss_actor_ID;
    u8 field_0x16[2];
    s16* boss_current_life;
    s16 boss_bar_health_max;
    s16 boss_bar_health_left;
    s16 boss_bar_damage;
    u8 field_0x22[2];
    f32 boss_bar_damage_length;
    MfdsState* gold_amount_textbox;
    MfdsState* item_amount_textbox;
    u8 field_0x30[4];
    u16* gold_amount_text;
    u16* item_amount_text;
    u8 field_0x3C[4];
} HUDParams;
typedef struct {
    ObjectHeader header;
    u8 field_0x20[4];
    Model* clock_and_health;
    Model* boss_bar;
    Model* status_and_subweapon;
    Model* gold_graphic;
    Model* day_graphic_above_clock;
    Model* clock_minute_marker;
    Model* clock_hour_marker;
    Model* health_bar_overlay;
    Model* health_bar_fill;
    Model* health_bar_fill_damage;
    Model* boss_bar_fill;
    Model* boss_bar_fill_damage;
    Model* status_text;
    Model* subweapon;
    Model* subweapon_icon;
    f32 day_and_night_switching_alpha;
    f32 day_and_night_switching_transition_progress;
    f32 day_and_night_switching_factor;
    u8 time_before_making_elements_static;
    u8 boss_bar_is_filling_up;
    s16 health_depletion_rate_while_poisoned;
    HUDParams* params;
} HUD;
extern void HUD_entrypoint(HUD* self);
extern void HUD_initParams(HUD* self);
extern void HUD_initGraphics(HUD* self);
extern void HUD_update(HUD* self);
extern void HUD_destroy(HUD* self);
void HUDParams_IncreaseDamage(s16 damage, u32 player_status);
void HUDParams_FillPlayerHealth(
    s16 life, u32 player_flags_to_remove, s32 play_character_health_fulfilled_sound
);
extern u8 player_has_max_health;
extern u8 play_health_recovery_sound;
typedef void (*HUD_func_t)(HUD*);

typedef enum GameplayMenuManagerFlag {
    IN_PAUSE_MENU = (1 << (0)),
    IN_FILE_SELECT = (1 << (1)),
    IN_OPTIONS_MENU = (1 << (2)),
    IN_GAMEPLAY = (1 << (3)),
    IN_QUIT_GAME = (1 << (4)),
    IN_GAME_OVER = (1 << (5)),
    IN_RENON_SHOP = (1 << (6))
} GameplayMenuManagerFlag;
typedef enum GameplayMenuManagerMenuState {
    ENTERING_PAUSE_MENU = (1 << (0)),
    ENTERING_FILE_SELECT = (1 << (1)),
    ENTERING_OPTION = (1 << (2)),
    EXIT_MENU = (1 << (3)),
    QUIT_GAME = (1 << (4)),
    ENTERING_GAME_OVER = (1 << (5)),
    ENTERING_RENON_SHOP = (1 << (6)),
    MENU_STATE_100 = (1 << (8)),
    INIT_NEW_GAME = (1 << (9))
} GameplayMenuManagerMenuState;
typedef struct GameplayMenuManager {
    ObjectHeader header;
    u8 field_0x20[32];
    s32 bought_item_from_renon_shop;
    u32 hide_common_textbox_window;
    u8 field_0x48[8];
    u32 update_assets_heap_block_max_size;
    void* assets_file_buffer_start_ptr;
    RGBA background_color;
    MfdsState* common_textbox;
    union {
        HUDParams* HUD_params;
        HUD* obj_hud;
    };
    u32 current_opened_menu;
    void* assets_file_buffer_end_ptr;
    u32 flags;
    u32 menu_state;
} GameplayMenuManager;
void GameplayMenuManager_entrypoint(GameplayMenuManager* self);
void GameplayMenuManager_initMainStructs(GameplayMenuManager* self);
void GameplayMenuManager_initHUDParams(GameplayMenuManager* self);
void GameplayMenuManager_outsideMenuLoop(GameplayMenuManager* self);
void GameplayMenuManager_initMenu(GameplayMenuManager* self);
void GameplayMenuManager_insideMenuLoop(GameplayMenuManager* self);
void GameplayMenuManager_exitMenu(GameplayMenuManager* self);
u32 moveSelectionCursor(u32 button);
MfdsState* GameplayCommonTextbox_getIfClosed(void);
MfdsState* GameplayCommonTextbox_close(void);
MfdsState* GameplayCommonTextbox_prepare(
    u16* text_ptr, u32 flags, u8 line, u16 width, u8 palette, s16 X_pos, s16 Y_pos, u8 display_time
);
MfdsState* GameplayCommonTextbox_addItemAndPrepareName(s32);
MfdsState* GameplayCommonTextbox_getMapMessage(u16, u8);
MfdsState* GameplayCommonTextbox_getMessageFromPool(u16*, u8, u8);
u32 GameplayCommonTextbox_lensAreOpened(void);
u32 GameplayCommonTextbox_lensAreClosed(void);
ObjMfds* GameplayCommonTextbox_getObject(s32, Object*);
ObjMfds* GameplayCommonTextbox_getObjectFromList(void);
typedef enum GameplayMenuManagerFuncID {
    GAMEPLAYMENUMGR_INIT_MAIN_STRUCTS,
    GAMEPLAYMENUMGR_INIT_HUD_PARAMS,
    GAMEPLAYMENUMGR_OUTSIDE_MENU_LOOP,
    GAMEPLAYMENUMGR_INIT_MENU,
    GAMEPLAYMENUMGR_INSIDE_MENU_LOOP,
    GAMEPLAYMENUMGR_EXIT_MENU,
    GAMEPLAYMENUMGR_DO_NOTHING
} GameplayMenuManagerFuncID;
typedef void (*GameplayMenuManagerFunc)(GameplayMenuManager*);
extern GameplayMenuManager* ptr_gameplayMenuMgr;

