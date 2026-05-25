from __future__ import annotations


def american_to_decimal(american_odds: int) -> float:
    if american_odds == 0:
        raise ValueError("American odds cannot be zero")
    if american_odds > 0:
        return 1.0 + (american_odds / 100.0)
    return 1.0 + (100.0 / abs(american_odds))


def american_to_implied_probability(american_odds: int) -> float:
    if american_odds == 0:
        raise ValueError("American odds cannot be zero")
    if american_odds > 0:
        return 100.0 / (american_odds + 100.0)
    return abs(american_odds) / (abs(american_odds) + 100.0)


def expected_value(probability: float, american_odds: int) -> float:
    decimal_odds = american_to_decimal(american_odds)
    return (probability * decimal_odds) - 1.0


def profit_for_result(stake_units: float, american_odds: int, won: bool) -> float:
    if not won:
        return -stake_units
    decimal_odds = american_to_decimal(american_odds)
    return stake_units * (decimal_odds - 1.0)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
