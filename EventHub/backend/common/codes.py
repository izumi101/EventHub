from secrets import choice
from string import digits


def generate_numeric_code(length: int = 6) -> str:
    return ''.join(choice(digits) for _ in range(length))

