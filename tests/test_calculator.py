"""
Tests for src/tools/calculator.py
"""

import pytest
from src.tools.calculator import calculate


class TestCalculator:
    """Tests for calculate function."""

    def test_basic_addition(self):
        assert calculate("2 + 2") == 4

    def test_basic_subtraction(self):
        assert calculate("10 - 3") == 7

    def test_multiplication(self):
        assert calculate("6 * 7") == 42

    def test_division(self):
        assert calculate("20 / 4") == 5

    def test_order_of_operations(self):
        """PEMDAS should be respected."""
        assert calculate("2 + 3 * 4") == 14

    def test_parentheses(self):
        assert calculate("(2 + 3) * 4") == 20

    def test_decimal_result(self):
        result = calculate("7 / 2")
        assert result == 3.5

    def test_negative_numbers(self):
        assert calculate("-5 + 10") == 5

    def test_complex_expression(self):
        result = calculate("(10 + 5) * 2 / 3")
        assert result == 10.0
