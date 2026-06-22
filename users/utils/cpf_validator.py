import re

def validate_cpf(cpf_str: str) -> bool:
    """
    Validates a Brazilian CPF number.
    Returns True if valid, False otherwise.
    """
    if not cpf_str:
        return False

    # Remove all non-digits
    cpf = re.sub(r'\D', '', cpf_str)

    # Check if it has exactly 11 digits
    if len(cpf) != 11:
        return False

    # Reject known invalid CPFs (all digits equal)
    if cpf == cpf[0] * 11:
        return False

    # Calculate first verification digit
    sum_1 = 0
    for i in range(9):
        sum_1 += int(cpf[i]) * (10 - i)
    remainder_1 = sum_1 % 11
    digit_1 = 0 if remainder_1 < 2 else 11 - remainder_1

    if int(cpf[9]) != digit_1:
        return False

    # Calculate second verification digit
    sum_2 = 0
    for i in range(10):
        sum_2 += int(cpf[i]) * (11 - i)
    remainder_2 = sum_2 % 11
    digit_2 = 0 if remainder_2 < 2 else 11 - remainder_2

    if int(cpf[10]) != digit_2:
        return False

    return True
