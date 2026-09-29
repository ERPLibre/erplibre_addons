# Copyright 2026 TechnoLibre - Mathieu Benoit
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Finite fields GF(q), q a prime power up to 49. See 01 §6."""

IRREDUCIBLES: dict[int, tuple[int, tuple[int, ...]]] = {
    4: (2, (1, 1, 1)),
    8: (2, (1, 1, 0, 1)),
    9: (3, (1, 0, 1)),
    16: (2, (1, 1, 0, 0, 1)),
    25: (5, (2, 0, 1)),
    27: (3, (1, 2, 0, 1)),
    32: (2, (1, 0, 1, 0, 0, 1)),
    49: (7, (1, 0, 1)),
}
# Coefficients from degree 0 to degree k, monic (top coefficient 1).
# These are the only prime-power orders composed up to 49; every other
# order this library ever builds a field for is itself prime.


def _is_prime(value: int) -> bool:
    """Return whether value has no factor between 2 and its square root."""
    if value < 2:
        return False
    factor = 2
    while factor * factor <= value:
        if value % factor == 0:
            return False
        factor += 1
    return True


def is_prime_power(q: int) -> bool:
    """Return whether q equals p**k for a prime p and an integer k >= 1."""
    if q < 2:
        return False
    remaining = q
    factor = 2
    prime = None
    while factor * factor <= remaining:
        if remaining % factor == 0:
            prime = factor
            while remaining % factor == 0:
                remaining //= factor
            break
        factor += 1
    if prime is None:
        return True  # no factor below its square root: q is itself prime
    return remaining == 1


def _digits(value: int, base: int, length: int) -> list[int]:
    """Return value written in base, least significant digit first."""
    digits = []
    for _ in range(length):
        digits.append(value % base)
        value //= base
    return digits


def _from_digits(digits: list[int], base: int) -> int:
    """Invert _digits: rebuild an integer from its base digit list."""
    value = 0
    for power, digit in enumerate(digits):
        value += digit * base**power
    return value


def _reduce(
    coefficients: list[int], modulus: tuple[int, ...], prime: int
) -> list[int]:
    """Reduce a polynomial modulo a monic one, coefficients modulo prime.

    coefficients holds the product of two degree-(k-1) polynomials, so
    its degree never exceeds 2k-2 and every index touched below already
    exists in the list - no padding is needed. Long division proceeds
    from the top degree down; since modulus is monic, subtracting its
    leading coefficient (1) times the current lead zeroes that degree
    out exactly.
    """
    coefficients = list(coefficients)
    k = len(modulus) - 1
    for degree in range(len(coefficients) - 1, k - 1, -1):
        lead = coefficients[degree]
        if lead == 0:
            continue
        shift = degree - k
        for power, factor in enumerate(modulus):
            index = shift + power
            coefficients[index] = (coefficients[index] - lead * factor) % prime
    return coefficients[:k]


def gf_tables(q: int) -> tuple[list[list[int]], list[list[int]]]:
    """Return the addition and multiplication tables of GF(q).

    add[x][y] and mul[x][y] give the sum and product of x and y, each
    an integer in 0..q-1. An element is that integer written in base p.
    For q prime, base p has a single digit and this is arithmetic
    modulo q. For a tabulated prime power, addition is digit-wise
    modulo p and multiplication is the product of the two digit lists
    as polynomials over GF(p), reduced modulo the irreducible from
    IRREDUCIBLES. Raises ValueError for a q that is not a prime power,
    or a prime power without a tabulated irreducible.
    """
    if q in IRREDUCIBLES:
        prime, modulus = IRREDUCIBLES[q]
        k = len(modulus) - 1
        add = [[0] * q for _ in range(q)]
        mul = [[0] * q for _ in range(q)]
        for x in range(q):
            dx = _digits(x, prime, k)
            for y in range(q):
                dy = _digits(y, prime, k)
                add[x][y] = _from_digits(
                    [(a + b) % prime for a, b in zip(dx, dy)], prime
                )
                product = [0] * (2 * k - 1)
                for i, a in enumerate(dx):
                    if a == 0:
                        continue
                    for j, b in enumerate(dy):
                        product[i + j] = (product[i + j] + a * b) % prime
                mul[x][y] = _from_digits(
                    _reduce(product, modulus, prime), prime
                )
        return add, mul
    if _is_prime(q):
        add = [[(x + y) % q for y in range(q)] for x in range(q)]
        mul = [[(x * y) % q for y in range(q)] for x in range(q)]
        return add, mul
    raise ValueError(f"no tabulated field of order {q}")
