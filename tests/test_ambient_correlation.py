"""
Tests for the ambient correlation rule (S3: Ambient → cooling-load correlation).

Scenarios tested:
  1. Warmup phase returns INSUFFICIENT_DATA
  2. Normal correlated data returns COOLING_LOAD_NORMAL
  3. A sudden power spike with no ambient change triggers COOLING_LOAD_HIGH
  4. A sudden power drop triggers COOLING_LOAD_LOW
  5. Pearson R is positive when temp and power are positively correlated
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from omniview.rules.ambient_correlation import AmbientCorrelationRule


def test_warmup_insufficient_data():
    """During warmup (< min_readings), the rule should return INSUFFICIENT_DATA."""
    rule = AmbientCorrelationRule(window_size=60, min_readings=15)

    for i in range(10):
        event = rule.evaluate(ambient_temp_c=25.0 + i * 0.1, active_power_kw=1800.0)

    assert event.event_type == "INSUFFICIENT_DATA"
    assert event.window_size == 10
    print("  ✅ test_warmup_insufficient_data OK")


def test_normal_correlated_data():
    """When power tracks temperature linearly, the rule should return NORMAL."""
    rule = AmbientCorrelationRule(window_size=60, sigma_threshold=2.0, min_readings=15)

    # Feed 30 readings where power = 1500 + 20 * temp (perfectly correlated)
    for i in range(30):
        temp = 22.0 + i * 0.5  # 22 → 36.5
        power = 1500.0 + 20.0 * temp
        event = rule.evaluate(ambient_temp_c=temp, active_power_kw=power)

    assert event.event_type == "COOLING_LOAD_NORMAL"
    assert event.correlation_r > 0.95
    print(f"  ✅ test_normal_correlated_data OK (R={event.correlation_r})")


def test_high_power_spike_detected():
    """A sudden power spike not justified by ambient should trigger COOLING_LOAD_HIGH."""
    rule = AmbientCorrelationRule(window_size=60, sigma_threshold=2.0, min_readings=15)

    # Build a stable baseline: 25°C → 1800 kW (with minor variation)
    for i in range(30):
        temp = 25.0 + (i % 3) * 0.2
        power = 1800.0 + (i % 3) * 5.0
        rule.evaluate(ambient_temp_c=temp, active_power_kw=power)

    # Now inject a massive power spike at the SAME temperature
    event = rule.evaluate(ambient_temp_c=25.2, active_power_kw=2500.0)

    assert event.event_type == "COOLING_LOAD_HIGH"
    assert event.residual_kw > 500
    assert event.residual_sigma > 2.0
    print(f"  ✅ test_high_power_spike_detected OK (residual={event.residual_kw} kW, {event.residual_sigma}σ)")


def test_low_power_drop_detected():
    """A sudden power drop should trigger COOLING_LOAD_LOW."""
    rule = AmbientCorrelationRule(window_size=60, sigma_threshold=2.0, min_readings=15)

    # Build a stable baseline
    for i in range(30):
        temp = 28.0 + (i % 3) * 0.1
        power = 1900.0 + (i % 3) * 3.0
        rule.evaluate(ambient_temp_c=temp, active_power_kw=power)

    # Power crashes while ambient stays the same — compressor tripped?
    event = rule.evaluate(ambient_temp_c=28.1, active_power_kw=1000.0)

    assert event.event_type == "COOLING_LOAD_LOW"
    assert event.residual_kw < -500
    assert event.residual_sigma < -2.0
    print(f"  ✅ test_low_power_drop_detected OK (residual={event.residual_kw} kW, {event.residual_sigma}σ)")


def test_positive_correlation():
    """Pearson R should be positive when hotter weather = more power."""
    rule = AmbientCorrelationRule(window_size=60, min_readings=15)

    for i in range(20):
        temp = 20.0 + i * 1.0   # 20 → 39
        power = 1600.0 + i * 15  # 1600 → 1885
        event = rule.evaluate(ambient_temp_c=temp, active_power_kw=power)

    assert event.correlation_r > 0.9
    print(f"  ✅ test_positive_correlation OK (R={event.correlation_r})")


def test_weather_justified_spike_is_normal():
    """If power rises BUT ambient also rose proportionally, it should be NORMAL."""
    rule = AmbientCorrelationRule(window_size=60, sigma_threshold=2.0, min_readings=15)

    # Train on a linear relationship: power = 1500 + 15 * temp
    for i in range(25):
        temp = 22.0 + i * 0.5
        power = 1500.0 + 15.0 * temp
        rule.evaluate(ambient_temp_c=temp, active_power_kw=power)

    # Now push temp to 38°C — power should be ~2070 kW and NOT be flagged
    event = rule.evaluate(ambient_temp_c=38.0, active_power_kw=2070.0)

    assert event.event_type == "COOLING_LOAD_NORMAL"
    print(f"  ✅ test_weather_justified_spike_is_normal OK (type={event.event_type}, σ={event.residual_sigma})")


if __name__ == "__main__":
    print("Running ambient correlation rule tests...")
    test_warmup_insufficient_data()
    test_normal_correlated_data()
    test_high_power_spike_detected()
    test_low_power_drop_detected()
    test_positive_correlation()
    test_weather_justified_spike_is_normal()
    print("\n✅ All ambient correlation tests passed.")
