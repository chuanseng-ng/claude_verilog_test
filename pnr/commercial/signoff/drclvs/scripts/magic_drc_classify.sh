#!/bin/bash
# magic_drc_classify.sh <report> <sram_boxes.txt> <out.tsv> <outside_sample.txt>
# STREAMS the Magic DRC report (>1 GB) with awk; never loads it into memory. Bug-for-bug the bead-45a logic: every violation
# bbox is classified as INSIDE (fully within one SRAM footprint), STRADDLE (intersects one but not fully inside) or OUTSIDE.
set -eu
rpt=$1; boxes=$2; out=$3; samp=$4
LC_ALL=C awk -v BOXES="$boxes" -v SAMP="$samp" '
BEGIN{ n=0; while ((getline l < BOXES) > 0) { split(l,a," "); n++; bx0[n]=a[2]; by0[n]=a[3]; bx1[n]=a[4]; by1[n]=a[5] } close(BOXES)
       tol=0.01; rule="(none)"; tot=0; ns=0 }
/^----/ {next}
/^\[INFO\]/ { if ($0 ~ /COUNT:/) cnt=$3; next }
/^ -?[0-9]/ {
  x0=$1+0; y0=$2+0; x1=$3+0; y1=$4+0; tot++; cls="O"
  for (i=1;i<=n;i++) {
    if (x0>=bx0[i]-tol && y0>=by0[i]-tol && x1<=bx1[i]+tol && y1<=by1[i]+tol) { cls="I"; break }
    if (x1>bx0[i] && x0<bx1[i] && y1>by0[i] && y0<by1[i]) cls="S"
  }
  if (cls=="I") ins[rule]++; else if (cls=="S") str[rule]++; else { out_[rule]++; if (ns<200000) { print rule "\t" $0 > SAMP; ns++ } }
  seen[rule]=1; next }
NR==1 {next}
{ rule=$0 }
END{ printf "rule\tinside_sram\tstraddle\toutside\n" > "'"$out"'"
     for (r in seen) printf "%s\t%d\t%d\t%d\n", r, ins[r], str[r], out_[r] > "'"$out"'"
     printf "# total_parsed=%d report_COUNT=%s\n", tot, cnt > "'"$out"'" }' "$rpt"
sort -t$'\t' -k4,4nr -o "$out.sorted" <(grep -v '^#' "$out") ; { head -1 "$out.sorted" | grep -q '^rule' && true; } ; 
{ echo -e "rule\tinside_sram\tstraddle\toutside"; grep -v '^rule' "$out.sorted"; grep '^#' "$out"; } > "$out.tmp" && mv "$out.tmp" "$out"; rm -f "$out.sorted"
awk -F'\t' 'NR>1 && !/^#/ {i+=$2; s+=$3; o+=$4} END{printf "TOTAL inside=%d straddle=%d outside=%d sum=%d\n", i,s,o,i+s+o}' "$out"
