import random

import pytest

from games.bot import choose_move
from games.logic import NEW_BOARD, empty_cells, is_over, next_symbol, place, winner


def _human_never_beats_hard_bot(board, rng):
    """Walk every move sequence the human (X) can play against the bot (O)."""
    if is_over(board):
        assert winner(board) != "X", board
        return
    if next_symbol(board) == "X":
        for i in empty_cells(board):
            _human_never_beats_hard_bot(place(board, i, "X"), rng)
    else:
        _human_never_beats_hard_bot(
            place(board, choose_move(board, "O", "hard", rng), "O"), rng
        )


def test_hard_bot_never_loses():
    _human_never_beats_hard_bot(NEW_BOARD, random.Random(1))


@pytest.mark.parametrize("level", ["medium", "hard"])
def test_bot_takes_a_win(level):
    #  O O -
    #  X X -
    #  X - -
    assert choose_move("OO-XX-X--", "O", level) == 2


@pytest.mark.parametrize("level", ["medium", "hard"])
def test_bot_blocks_a_loss(level):
    #  X X -
    #  - O -
    #  - - -
    assert choose_move("XX--O----", "O", level) == 2


def test_easy_bot_plays_a_legal_move():
    rng = random.Random(3)
    for _ in range(20):
        assert choose_move("XOX-O----", "X", "easy", rng) in empty_cells("XOX-O----")
