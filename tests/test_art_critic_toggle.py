"""Tests for the ART_CRITIC_ENABLED switch on the daily image's art critic."""

import pytest

import main


@pytest.mark.parametrize("value", [None, "", "false", "0", "no"])
def test_art_critic_is_off_unless_enabled(value, monkeypatch):
    if value is None:
        monkeypatch.delenv("ART_CRITIC_ENABLED", raising=False)
    else:
        monkeypatch.setenv("ART_CRITIC_ENABLED", value)
    # Even a guaranteed roll must not fire when the switch is off.
    monkeypatch.setattr(main.random, "random", lambda: 0.0)

    assert main.should_run_art_critic() is False


@pytest.mark.parametrize("value", ["true", "TRUE", "1"])
def test_art_critic_fires_on_probability_when_enabled(value, monkeypatch):
    monkeypatch.setenv("ART_CRITIC_ENABLED", value)

    monkeypatch.setattr(main.random, "random", lambda: 0.0)
    assert main.should_run_art_critic() is True

    monkeypatch.setattr(main.random, "random", lambda: 0.99)
    assert main.should_run_art_critic() is False
