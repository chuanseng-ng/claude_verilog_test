foreach c {set_dft_config report_dft_config preview_dft insert_dft scan_replace execute_dft_plan} {
  puts "$c : [llength [info commands $c]]"
}
puts "dft-ish: [lsort [info commands *dft*]]"
puts "scan-ish: [lsort [info commands *scan*]]"
