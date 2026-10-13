import pytest

from games.logic import (
    NEW_BOARD,
    WIN_LINES,
    is_draw,
    next_symbol,
    place,
    winner,
    winning_line,
)


@pytest.mark.parametrize("line", WIN_LINES)
@pytest.mark.parametrize("symbol", ["X", "O"])
def test_every_line_wins(line, symbol):
    board = NEW_BOARD
    for i in line:
        board = place(board, i, symbol)
    assert winner(board) == symbol
    assert winning_line(board) == line


def test_empty_board_has_no_winner():
    assert winner(NEW_BOARD) is None
    assert not is_draw(NEW_BOARD)


def test_full_board_without_line_is_draw():
    board = "XOXXOOOXX"
    assert winner(board) is None
    assert is_draw(board)


def test_x_moves_first_then_turns_alternate():
    assert next_symbol(NEW_BOARD) == "X"
    assert next_symbol(place(NEW_BOARD, 4, "X")) == "O"
    assert next_symbol("XO-------") == "X"
