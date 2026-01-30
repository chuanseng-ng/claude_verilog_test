#=============================================
# SDC Constraint Verification Script
# File: check_constraints.tcl
# Purpose: Verify that all ports are properly constrained
#=============================================

puts "\n=========================================="
puts "SDC Constraint Verification"
puts "==========================================\n"

# Count total ports
set all_ports [all_ports]
set num_total_ports [llength $all_ports]
puts "Total ports in design: $num_total_ports"

#---------------------------------------------
# Check Clock Definitions
#---------------------------------------------
puts "\n--- Clock Definitions ---"
set clocks [all_clocks]
if {[llength $clocks] == 0} {
    puts "ERROR: No clocks defined!"
    set clock_ok 0
} else {
    puts "Clocks defined: [llength $clocks]"
    foreach clk $clocks {
        set period [get_attribute [get_clocks $clk] period]
        set freq [expr 1000.0 / $period]
        puts "  - $clk: period=${period}ns, freq=${freq}MHz"
    }
    set clock_ok 1
}

#---------------------------------------------
# Check Input Delays
#---------------------------------------------
puts "\n--- Input Delay Constraints ---"
set input_ports [all_inputs]
set num_inputs [llength $input_ports]
set constrained_inputs 0
set unconstrained_inputs [list]

foreach port $input_ports {
    set port_name [get_object_name $port]

    # Skip clock and reset ports
    if {[string match "*clk*" $port_name] || [string match "*rst*" $port_name]} {
        continue
    }

    # Check if port has input delay
    set has_delay 0
    catch {
        set delays [get_attribute $port input_delay]
        if {[llength $delays] > 0} {
            set has_delay 1
            incr constrained_inputs
        }
    }

    if {!$has_delay} {
        lappend unconstrained_inputs $port_name
    }
}

puts "Constrained inputs: $constrained_inputs / $num_inputs"
if {[llength $unconstrained_inputs] > 0} {
    puts "WARNING: Unconstrained input ports:"
    foreach port $unconstrained_inputs {
        puts "  - $port"
    }
}

#---------------------------------------------
# Check Output Delays
#---------------------------------------------
puts "\n--- Output Delay Constraints ---"
set output_ports [all_outputs]
set num_outputs [llength $output_ports]
set constrained_outputs 0
set unconstrained_outputs [list]

foreach port $output_ports {
    set port_name [get_object_name $port]

    # Check if port has output delay
    set has_delay 0
    catch {
        set delays [get_attribute $port output_delay]
        if {[llength $delays] > 0} {
            set has_delay 1
            incr constrained_outputs
        }
    }

    if {!$has_delay} {
        lappend unconstrained_outputs $port_name
    }
}

puts "Constrained outputs: $constrained_outputs / $num_outputs"
if {[llength $unconstrained_outputs] > 0} {
    puts "WARNING: Unconstrained output ports:"
    foreach port $unconstrained_outputs {
        puts "  - $port"
    }
}

#---------------------------------------------
# Check False Paths
#---------------------------------------------
puts "\n--- False Path Constraints ---"
set false_paths [list]
catch {
    set false_paths [get_attribute [current_design] false_path]
}
puts "False paths defined: [llength $false_paths]"

#---------------------------------------------
# Check Clock Uncertainty
#---------------------------------------------
puts "\n--- Clock Uncertainty ---"
if {$clock_ok} {
    foreach clk $clocks {
        set uncertainty "N/A"
        catch {
            set uncertainty [get_attribute [get_clocks $clk] uncertainty]
        }
        puts "  - $clk: uncertainty=${uncertainty}ns"
    }
}

#---------------------------------------------
# Check Design Rule Constraints
#---------------------------------------------
puts "\n--- Design Rule Constraints ---"

# Max transition
set max_trans "not set"
catch {
    set max_trans [get_attribute [current_design] max_transition]
}
puts "Max transition: $max_trans"

# Max capacitance
set max_cap "not set"
catch {
    set max_cap [get_attribute [current_design] max_capacitance]
}
puts "Max capacitance: $max_cap"

# Max fanout
set max_fanout "not set"
catch {
    set max_fanout [get_attribute [current_design] max_fanout]
}
puts "Max fanout: $max_fanout"

#---------------------------------------------
# Check for Unconstrained Paths
#---------------------------------------------
puts "\n--- Unconstrained Path Analysis ---"
puts "Checking for unconstrained paths..."
puts "(This may take a moment...)"

# Try to report unconstrained paths
catch {
    set unconstrained_file "reports/unconstrained_paths.rpt"
    report_checks -unconstrained -path_delay max -format full_clock > $unconstrained_file
    puts "Unconstrained path report saved to: $unconstrained_file"
}

#---------------------------------------------
# Summary
#---------------------------------------------
puts "\n=========================================="
puts "Summary"
puts "==========================================\n"

set warnings 0
set errors 0

if {!$clock_ok} {
    puts "ERROR: No clocks defined"
    incr errors
}

if {[llength $unconstrained_inputs] > 0} {
    puts "WARNING: [llength $unconstrained_inputs] unconstrained input(s)"
    incr warnings
}

if {[llength $unconstrained_outputs] > 0} {
    puts "WARNING: [llength $unconstrained_outputs] unconstrained output(s)"
    incr warnings
}

if {$errors == 0 && $warnings == 0} {
    puts "PASS: All ports are properly constrained!"
} else {
    puts "ISSUES FOUND:"
    puts "  Errors: $errors"
    puts "  Warnings: $warnings"
    puts "\nPlease review and fix the issues above."
}

puts "\n==========================================\n"

# Return status (0 = success, 1 = issues found)
if {$errors > 0} {
    return 1
} else {
    return 0
}
