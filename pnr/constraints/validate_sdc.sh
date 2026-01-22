#!/bin/bash
#================================================================
# SDC Validation Helper Script
# Quick validation of SDC files without full STA run
#================================================================

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default SDC file
SDC_FILE="${1:-phase1_cpu_enhanced.sdc}"

echo -e "${BLUE}=========================================="
echo "SDC Validation Script"
echo -e "==========================================${NC}\n"

# Check if file exists
if [ ! -f "$SDC_FILE" ]; then
    echo -e "${RED}ERROR: SDC file not found: $SDC_FILE${NC}"
    exit 1
fi

echo -e "${GREEN}✓${NC} Found SDC file: $SDC_FILE"
echo ""

# Initialize counters
ERRORS=0
WARNINGS=0
CHECKS=0

#----------------------------------------------------------------
# Basic Syntax Checks
#----------------------------------------------------------------

echo -e "${BLUE}--- Basic Syntax Checks ---${NC}"

# Check for clock definition
CHECKS=$((CHECKS + 1))
if grep -q "^[[:space:]]*create_clock" "$SDC_FILE"; then
    CLOCKS=$(grep "^[[:space:]]*create_clock" "$SDC_FILE" | wc -l)
    echo -e "${GREEN}✓${NC} Clock definition found ($CLOCKS clock(s))"
else
    echo -e "${RED}✗${NC} No clock definition found"
    ERRORS=$((ERRORS + 1))
fi

# Check for clock uncertainty
CHECKS=$((CHECKS + 1))
if grep -q "set_clock_uncertainty" "$SDC_FILE"; then
    echo -e "${GREEN}✓${NC} Clock uncertainty defined"
else
    echo -e "${YELLOW}!${NC} No clock uncertainty found"
    WARNINGS=$((WARNINGS + 1))
fi

# Check for input delays
CHECKS=$((CHECKS + 1))
if grep -q "set_input_delay" "$SDC_FILE"; then
    INPUT_DELAYS=$(grep "set_input_delay" "$SDC_FILE" | wc -l)
    echo -e "${GREEN}✓${NC} Input delays found ($INPUT_DELAYS constraint(s))"
else
    echo -e "${YELLOW}!${NC} No input delays found"
    WARNINGS=$((WARNINGS + 1))
fi

# Check for output delays
CHECKS=$((CHECKS + 1))
if grep -q "set_output_delay" "$SDC_FILE"; then
    OUTPUT_DELAYS=$(grep "set_output_delay" "$SDC_FILE" | wc -l)
    echo -e "${GREEN}✓${NC} Output delays found ($OUTPUT_DELAYS constraint(s))"
else
    echo -e "${YELLOW}!${NC} No output delays found"
    WARNINGS=$((WARNINGS + 1))
fi

# Check for false paths
CHECKS=$((CHECKS + 1))
if grep -q "set_false_path" "$SDC_FILE"; then
    FALSE_PATHS=$(grep "set_false_path" "$SDC_FILE" | wc -l)
    echo -e "${GREEN}✓${NC} False paths defined ($FALSE_PATHS path(s))"
else
    echo -e "${YELLOW}!${NC} No false paths defined"
    # This is just a warning, not an error
fi

echo ""

#----------------------------------------------------------------
# Content Validation
#----------------------------------------------------------------

echo -e "${BLUE}--- Content Validation ---${NC}"

# Check for reset false path
CHECKS=$((CHECKS + 1))
if grep -q "set_false_path.*rst" "$SDC_FILE"; then
    echo -e "${GREEN}✓${NC} Reset marked as false path"
else
    echo -e "${YELLOW}!${NC} Reset not marked as false path (may be intentional)"
    WARNINGS=$((WARNINGS + 1))
fi

# Check for design rules
CHECKS=$((CHECKS + 1))
if grep -q "set_max_transition\|set_max_capacitance\|set_max_fanout" "$SDC_FILE"; then
    echo -e "${GREEN}✓${NC} Design rule constraints found"
else
    echo -e "${YELLOW}!${NC} No design rule constraints found"
    WARNINGS=$((WARNINGS + 1))
fi

# Check for load/drive constraints
CHECKS=$((CHECKS + 1))
if grep -q "set_load\|set_driving_cell\|set_input_transition" "$SDC_FILE"; then
    echo -e "${GREEN}✓${NC} Load/drive constraints found"
else
    echo -e "${YELLOW}!${NC} No load/drive constraints found"
    WARNINGS=$((WARNINGS + 1))
fi

echo ""

#----------------------------------------------------------------
# Port Coverage Analysis
#----------------------------------------------------------------

echo -e "${BLUE}--- Port Coverage Analysis ---${NC}"

# Expected port groups
EXPECTED_AXI_INPUTS=("axi_arready" "axi_rdata" "axi_rvalid" "axi_awready" "axi_wready" "axi_bvalid")
EXPECTED_AXI_OUTPUTS=("axi_araddr" "axi_arvalid" "axi_awaddr" "axi_awvalid" "axi_wdata" "axi_wvalid" "axi_rready" "axi_bready")
EXPECTED_APB_INPUTS=("apb_paddr" "apb_psel" "apb_penable" "apb_pwrite" "apb_pwdata")
EXPECTED_APB_OUTPUTS=("apb_prdata" "apb_pready" "apb_pslverr")

# Check AXI input coverage
MISSING_AXI_IN=0
for port in "${EXPECTED_AXI_INPUTS[@]}"; do
    if ! grep -q "$port" "$SDC_FILE"; then
        if [ $MISSING_AXI_IN -eq 0 ]; then
            echo -e "${YELLOW}Missing AXI input constraints:${NC}"
        fi
        echo "  - $port"
        MISSING_AXI_IN=$((MISSING_AXI_IN + 1))
    fi
done

if [ $MISSING_AXI_IN -eq 0 ]; then
    echo -e "${GREEN}✓${NC} All expected AXI inputs constrained"
else
    WARNINGS=$((WARNINGS + MISSING_AXI_IN))
fi

# Check AXI output coverage
MISSING_AXI_OUT=0
for port in "${EXPECTED_AXI_OUTPUTS[@]}"; do
    if ! grep -q "$port" "$SDC_FILE"; then
        if [ $MISSING_AXI_OUT -eq 0 ]; then
            echo -e "${YELLOW}Missing AXI output constraints:${NC}"
        fi
        echo "  - $port"
        MISSING_AXI_OUT=$((MISSING_AXI_OUT + 1))
    fi
done

if [ $MISSING_AXI_OUT -eq 0 ]; then
    echo -e "${GREEN}✓${NC} All expected AXI outputs constrained"
else
    WARNINGS=$((WARNINGS + MISSING_AXI_OUT))
fi

# Check APB coverage
MISSING_APB=0
for port in "${EXPECTED_APB_INPUTS[@]}" "${EXPECTED_APB_OUTPUTS[@]}"; do
    if ! grep -q "$port" "$SDC_FILE"; then
        if [ $MISSING_APB -eq 0 ]; then
            echo -e "${YELLOW}Missing APB constraints:${NC}"
        fi
        echo "  - $port"
        MISSING_APB=$((MISSING_APB + 1))
    fi
done

if [ $MISSING_APB -eq 0 ]; then
    echo -e "${GREEN}✓${NC} All expected APB ports constrained"
else
    WARNINGS=$((WARNINGS + MISSING_APB))
fi

echo ""

#----------------------------------------------------------------
# File Statistics
#----------------------------------------------------------------

echo -e "${BLUE}--- File Statistics ---${NC}"
TOTAL_LINES=$(wc -l < "$SDC_FILE")
COMMENT_LINES=$(grep -c "^[[:space:]]*#" "$SDC_FILE" || true)
BLANK_LINES=$(grep -c "^[[:space:]]*$" "$SDC_FILE" || true)
CODE_LINES=$((TOTAL_LINES - COMMENT_LINES - BLANK_LINES))

echo "Total lines:   $TOTAL_LINES"
echo "Code lines:    $CODE_LINES"
echo "Comment lines: $COMMENT_LINES"
echo "Blank lines:   $BLANK_LINES"
echo ""

#----------------------------------------------------------------
# Summary
#----------------------------------------------------------------

echo -e "${BLUE}=========================================="
echo "Summary"
echo -e "==========================================${NC}\n"

echo "File: $SDC_FILE"
echo "Checks performed: $CHECKS"
echo ""

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ PASS: SDC file validation successful!${NC}"
    echo ""
    echo "No errors or warnings found."
    exit 0
else
    if [ $ERRORS -gt 0 ]; then
        echo -e "${RED}✗ FAIL: $ERRORS error(s) found${NC}"
    fi
    if [ $WARNINGS -gt 0 ]; then
        echo -e "${YELLOW}! WARNING: $WARNINGS warning(s) found${NC}"
    fi
    echo ""
    echo "Please review the issues above."

    if [ $ERRORS -gt 0 ]; then
        exit 1
    else
        exit 0
    fi
fi
