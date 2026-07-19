.option post=0 measout=0 statfl=1 co=128 measfail=0 ingold=2 gmindc=1e-18 finesim_mcbrief=0

.temp '(25) +(0)'
.param VOP='(0.75) +(0)'
.param VOPP=VOP
.param PU_W=' (87)*1n+(0*1n)'
.param PU_L=' (20)*1n+(0*1n)'
.param PG_W=' (174)*1n+(0*1n)'
.param PG_L=' (20)*1n+(0*1n)'
.param PD_W=' (174)*1n+(0*1n)'
.param PD_L=' (20)*1n+(0*1n)'

.param NFIN_PU='1'
.param NFIN_PG='2'
.param NFIN_PD='2'

.param VTMSKEW_PU1=' (0) + (0)'
.param VTMSKEW_PG1=' (0) + (0)'
.param VTMSKEW_PD1=' (0) + (0)'
.param VTMSKEW_PU2=' (0) + (0)'
.param VTMSKEW_PG2=' (0) + (0)'
.param VTMSKEW_PD2=' (0) + (0)'

.param VTSGSKEW_PU1=' (1) + (0)'
.param VTSGSKEW_PG1=' (1) + (0)'
.param VTSGSKEW_PD1=' (1) + (0)'
.param VTSGSKEW_PU2=' (1) + (0)'
.param VTSGSKEW_PG2=' (1) + (0)'
.param VTSGSKEW_PD2=' (1) + (0)'

.param VTSLSKEW_PU1=' (1) + (0)'
.param VTSLSKEW_PG1=' (1) + (0)'
.param VTSLSKEW_PD1=' (1) + (0)'
.param VTSLSKEW_PU2=' (1) + (0)'
.param VTSLSKEW_PG2=' (1) + (0)'
.param VTSLSKEW_PD2=' (1) + (0)'

.param MOMSKEW_PU1=' (1) + (0)'
.param MOMSKEW_PG1=' (1) + (0)'
.param MOMSKEW_PD1=' (1) + (0)'
.param MOMSKEW_PU2=' (1) + (0)'
.param MOMSKEW_PG2=' (1) + (0)'
.param MOMSKEW_PD2=' (1) + (0)'

.param VDDA='(0.75) +(0)'
.param VSSA=0
.param VWL='(0.75) +(0)'
.param VBL='(0.75) +(0)'
.param VNW='(0.75) +(0)'
.param VPW=0

.param VON='-VOPP'

.prot
.lib "//......./...lib" TT
.unprot

.param mc_global=0 fet_dop_mm=1 fet_geo_mm=1
.param gwells=0 gstis=0 pre_layout_sw=1

.global vdda vssa b1 b2 w1 w2 nwell pwell

.subckt hc1 in out
xmpu out in vdda nwell <pu fet 이름> nfin=NFIN_PU L='PU_L'
xmpg b1 w1 out pwell <pg fet 이름> nfin=NFIN_PG L='PG_L'
xmpd out in vssa pwell <pd fet 이름> nfin=NFIN_PD L='PD_L'
.ends hc1
.subckt hc2 in out
xmpu out in vdda nwell <pu fet 이름> nfin=NFIN_PU L='PU_L'
xmpg b2 w2 out pwell <pg fet 이름> nfin=NFIN_PG L='PG_L'
xmpd out in vssa pwell <pd fet 이름> nfin=NFIN_PD L='PD_L'
.ends hc2

vdda vdda 0 DC VDDA
vssa vssa 0 DC VSSA
vbl1 b1 0 DC VBL
vbl2 b2 0 DC VBL
vwl1 w1 0 DC VWL
vwl2 w2 0 DC VWL
vnwell nwell 0 DC VNW
vpwell pwell 0 DC VPW

xhc1 hc1in hc1out hc1
xhc2 hc2in hc2out hc2

vu u 0
.dc vu '-VOP' VOP 0.01 sweep monte=5000

Ehc1nv v1 0 vol='v(hc1out)*sqrt(2)+v(u)'
Ehv2nv v2 0 vol='v(hc2out)*sqrt(2)-v(u)'
Ehc1in hc1in 0 vol='v(u)/sqrt(2)+v(v1)/sqrt(2)'
Ehc2in hc2in 0 vol='-v(u)/sqrt(2)+v(v2)/sqrt(2)'

.measure dc xc1 when v(v1)=v(v2) cross=1 print=0
.measure dc xc2 when v(v1)=v(v2) croess=2 print=0
.measure dc xc3 when v(v1)=v(v2) croess=3 print=0
.measure dc xc4 when v(v1)=v(v2) croess=4 print=0
.measure dc xclast when v(v1)=v(v2) cross=last print=0
.measure dc xcount param="xc1==xclast ? 1:xc2==xclast ? 2:xc3==xclast ? 3"xc4==xclast ? 4:5" print=0
.measure dc y1 min par('abs(v(v1,v2))') from='-VOP/sqrt(2)' to=0 print=0
.measure dc y2 min par('abs(v(v1,v2))') from=0 to='VOP/sqrt(2)' print=0
.measure dc safnm param="xclast>0? -y1:-y2" print=0
.measure dc snmr1_diagonal max v(v1,v2) from='-VOP/sqrt(2)' to='VOP/3' print=0
.measure dc snmr2_diagonal max v(v2,v1) from='-VOP/3' to='VOP/sqrt(2)' print=0
.measure dc snmr_diagonal param="xc1==xclast ? safnm:min(snmr1_diagonal,snmr2_diagonal)" print=1

.end