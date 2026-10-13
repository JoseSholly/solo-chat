"""Tic-Tac-Toe rules. Pure functions over a 9-character board string.

Cells are indexed 0–8, left to right, top to bottom. "-" is an empty cell.
"""

EMPTY = "-"
X = "X"
O = "O"  # noqa: E741
NEW_BOARD = EMPTY * 9

WIN_LINES = (
    (0, 1, 2),
    (3, 4, 5),
    (6, 7, 8),
    (0, 3, 6),
    (1, 4, 7),
    (2, 5, 8),
    (0, 4, 8),
    (2, 4, 6),
)


def other(symbol: str) -> str:
    return O if symbol == X else X


def winning_line(board: str) -> tuple[int, int, int] | None:
    for a, b, c in WIN_LINES:
        if board[a] != EMPTY and board[a] == board[b] == board[c]:
            return (a, b, c)
    return None


def winner(board: str) -> str | None:
    line = winning_line(board)
    return board[line[0]] if line else None


def is_full(board: str) -> bool:
    return EMPTY not in board


def is_draw(board: str) -> bool:
    return is_full(board) and winner(board) is None


def is_over(board: str) -> bool:
    return winner(board) is not None or is_full(board)


def next_symbol(board: str) -> str:
    """X always moves first, so whose turn it is follows from the counts."""
    return X if board.count(X) == board.count(O) else O


def empty_cells(board: str) -> list[int]:
    return [i for i, c in enumerate(board) if c == EMPTY]


def place(board: str, index: int, symbol: str) -> str:
    return board[:index] + symbol + board[index + 1 :]
