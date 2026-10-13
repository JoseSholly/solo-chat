"""Computer opponent for Tic-Tac-Toe.

easy   — random empty cell
medium — takes a win, blocks a loss, otherwise random
hard   — minimax; never loses
"""

import random
from functools import lru_cache

from .logic import empty_cells, is_full, other, place, winner

LEVELS = ("easy", "medium", "hard")


def _finishing_move(board: str, symbol: str) -> int | None:
    for i in empty_cells(board):
        if winner(place(board, i, symbol)) == symbol:
            return i
    return None


@lru_cache(maxsize=None)
def _minimax(board: str, to_move: str, me: str) -> int:
    """Score of `board` for `me` with `to_move` to play: +10 win, -10 loss, 0 draw.
    Faster wins (and slower losses) score further from zero."""
    w = winner(board)
    if w is not None:
        depth = 9 - board.count("-")
        return (10 - depth) if w == me else (depth - 10)
    if is_full(board):
        return 0
    scores = [
        _minimax(place(board, i, to_move), other(to_move), me)
        for i in empty_cells(board)
    ]
    return max(scores) if to_move == me else min(scores)


def _best_move(board: str, symbol: str, rng: random.Random) -> int:
    scored = [
        (_minimax(place(board, i, symbol), other(symbol), symbol), i)
        for i in empty_cells(board)
    ]
    best = max(score for score, _ in scored)
    return rng.choice([i for score, i in scored if score == best])


def choose_move(board: str, symbol: str, level: str, rng=None) -> int:
    rng = rng or random
    cells = empty_cells(board)
    if not cells:
        raise ValueError("No moves left")
    if level == "hard":
        return _best_move(board, symbol, rng)
    if level == "medium":
        win = _finishing_move(board, symbol)
        if win is not None:
            return win
        block = _finishing_move(board, other(symbol))
        if block is not None:
            return block
    return rng.choice(cells)
