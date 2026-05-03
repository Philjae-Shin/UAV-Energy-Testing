# Energy Stress Mission Experiment
# Runs 3 custom-designed missions inside the Aerialist container
# Each mission targets different energy bug patterns

echo " Energy Stress Mission Experiment"

RESULTS_DIR="/src/aerialist/results"
TESTS_DIR="/src/aerialist/samples/tests"
FLIGHTS_DIR="/src/aerialist/samples/flights"
BASE_YAML="/src/aerialist/samples/tests/mission1.yaml"

# Mission names and their .plan files (mounted into container)
MISSIONS=("stress_hover" "stress_zigzag" "stress_altitude")
DESCRIPTIONS=(
    "Long hover (30s loiter) - energy vampire detection"
    "6-waypoint zigzag - motor inefficiency & drain spikes"
    "Altitude variation (5-25m) - climb/descend energy cost"
)

TOTAL=${#MISSIONS[@]}
CURRENT=0
FAILED=0

for i in "${!MISSIONS[@]}"; do
    CURRENT=$((CURRENT + 1))
    MNAME="${MISSIONS[$i]}"
    DESC="${DESCRIPTIONS[$i]}"
    TEST_YAML="$TESTS_DIR/${MNAME}.yaml"

    echo ""
    echo "[$CURRENT/$TOTAL] $MNAME: $DESC"

    # Record .ulg count before
    ULG_COUNT_BEFORE=$(ls "$RESULTS_DIR"/*.ulg 2>/dev/null | wc -l)

    # Copy .plan file to flights directory
    cp "/src/aerialist/stress_plans/${MNAME}.plan" "$FLIGHTS_DIR/${MNAME}.plan"

    # Create YAML test config from base template
    cp "$BASE_YAML" "$TEST_YAML"
    # Update mission file reference
    sed -i "s|mission_file:.*|mission_file: samples/flights/${MNAME}.plan|" "$TEST_YAML"

    echo "  Running simulation..."
    python3 aerialist exec --test "$TEST_YAML"

    # Check for new .ulg
    ULG_COUNT_AFTER=$(ls "$RESULTS_DIR"/*.ulg 2>/dev/null | wc -l)
    if [ "$ULG_COUNT_AFTER" -gt "$ULG_COUNT_BEFORE" ]; then
        LATEST_ULG=$(ls -t "$RESULTS_DIR"/*.ulg 2>/dev/null | head -1)
        mv "$LATEST_ULG" "$RESULTS_DIR/${MNAME}.ulg"
        echo "  → Success: ${MNAME}.ulg"
    else
        echo "  → FAILED: no new .ulg generated"
        FAILED=$((FAILED + 1))
    fi

    # Wait between runs
    if [ "$CURRENT" -lt "$TOTAL" ]; then
        echo "  Waiting 15s for simulator cleanup..."
        sleep 15
    fi
done

echo ""
echo " Experiment Complete"
echo " Total: $TOTAL | Failed: $FAILED"
echo ""
echo "Results:"
ls -la "$RESULTS_DIR"/*.ulg 2>/dev/null
