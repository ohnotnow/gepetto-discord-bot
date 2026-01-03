from mathparse import mathparse

def calculate(expression: str) -> float:
    return mathparse.parse(expression)
