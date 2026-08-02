"""
SHADOW CASE — mini-game mechanics.

lockpick: a Mastermind-style 3-digit (1-6) code guessing game with
exact/partial feedback, used to unlock the one locked location per case.

assembly: an ordered-sequence puzzle — the player must select collected
parts in one specific (randomized per case) order to repair the radio.
"""


def lockpick_feedback(code: list[int], guess: list[int]) -> tuple[int, int]:
    """Returns (exact_matches, partial_matches) mastermind-style."""
    exact = sum(1 for c, g in zip(code, guess) if c == g)

    code_remaining = [c for c, g in zip(code, guess) if c != g]
    guess_remaining = [g for c, g in zip(code, guess) if c != g]

    partial = 0
    for g in guess_remaining:
        if g in code_remaining:
            code_remaining.remove(g)
            partial += 1

    return exact, partial


def parse_code(code_str: str) -> list[int]:
    return [int(x) for x in code_str.split(",")]


def assembly_check_next(order: list[str], progress: int, chosen_name: str) -> bool:
    """Returns True if chosen_name is the correct next part in the sequence."""
    if progress >= len(order):
        return False
    return order[progress] == chosen_name


def parse_order(order_str: str) -> list[str]:
    return order_str.split(",")
