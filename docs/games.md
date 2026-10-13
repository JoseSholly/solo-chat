# Games

Solo-Chat has a **Games** section next to your rooms. The first game is **Tic-Tac-Toe**. You can play anyone who's online, look someone up by username, get matched with whoever is waiting, or play the computer when nobody's around.

- [Playing](#playing)
- [Finding an opponent](#finding-an-opponent)
- [Playing the bot](#playing-the-bot)
- [Rules and fairness](#rules-and-fairness)
- [Records](#records)
- [The board](#the-board)
- [How it's built](#how-its-built)
- [Adding another game](#adding-another-game)

## Playing

1. Open **Games** at the top of the sidebar (or **Play Tic-Tac-Toe** on the dashboard's welcome screen). The address becomes `/dashboard/?games`.
2. Pick an opponent: challenge someone, use **Quick match**, or **Play vs Bot**.
3. The board opens at `/dashboard/?game=<id>`. X always moves first. Take turns until someone gets three in a row or the board fills up.
4. When the game ends you can play a **Rematch** or go **Back to games**. You can also **Resign** at any point; it counts as a loss.

Games in progress are listed in the lobby under **Games in progress**, so you can leave and come back with **Resume**.

## Finding an opponent

### Who counts as online

You're online while you have the dashboard open in at least one tab. The dashboard's notification connection doubles as your presence. It sends a heartbeat every 30 seconds, and you drop off the list 90 seconds after the last one. Closing your last tab also takes you out of the Quick match queue.

### Challenge someone

- **Players** in the lobby lists everyone else who's online, with their record. Press **Challenge**.
- **Search** by username or display name to find a particular person. Search covers everyone, but only people who are online can be challenged; the rest show as *Offline*.
- You can also challenge someone from their profile card inside a room (**Challenge to Tic-Tac-Toe**).

The person you challenge gets a pop-up wherever they are on the dashboard: **Accept** or **Decline**. Closing the pop-up without answering counts as declining, so nobody is left waiting. If they accept, the board opens for both of you. The challenger plays X.

Challenges expire after **2 minutes**. Until then the challenger can withdraw theirs from **Waiting for an answer**. You can only have one open challenge or game with the same person at a time. If you challenge them again while a game is in progress, that game opens instead.

### Quick match

**Quick match** pairs you with the next person who is also looking. Who plays X is random. While you wait, the lobby shows a timer and keeps checking. If nobody turns up within 15 seconds, or if nobody else is online at all, it offers a game against the bot instead. Leaving the lobby stops the search.

## Playing the bot

The bot is always available and has three levels. Your last choice is remembered.

| Level | How it plays |
|---|---|
| Easy | Picks any free square |
| Medium | Takes a winning move when it has one and blocks yours; otherwise picks any free square |
| Hard | Looks ahead through every possible game (minimax) and never loses; the best you can do is a draw |

You always play X and move first. The bot replies about half a second after your move. Bot games are saved like any other, but they don't count toward your record against people (see [Records](#records)).

## Rules and fairness

The server checks every move. The browser only displays the result.

- Only the game's two players can open its connection or see it.
- A move is rejected if the game isn't being played, it isn't your turn, the square is taken, or the index isn't 0–8. The rejection goes back only to you.
- Whose turn it is comes from the board itself (X moves first), so it can't drift out of sync.
- Each move locks the game row while it is applied, so two moves can never land at the same time.
- A win is three in a row horizontally, vertically or diagonally. A full board with no line is a draw.

## Records

Your record is **won · lost · drawn** against people. It appears in the lobby, next to each player in the list, and on profile cards. Bot games are kept separately as a **vs Bot** record in the lobby. Records are always counted from finished games rather than stored, so they can't disagree with the games themselves.

## The board

The board uses no graphics library: it's plain HTML buttons, inline SVG and CSS, styled with the same design tokens as the rest of the app.

- **Marks:** X is two strokes in the accent green and O is a ring in a cool blue, so the two players differ by shape *and* colour. New marks draw themselves in with a short stroke animation.
- **Your turn:** empty squares show a faint preview of your mark on hover or focus. When it's not your turn the board doesn't respond, and the player whose turn it is gets a highlighted card above the board.
- **Last move** gets a subtle outline. **Winning line:** a stroke is drawn across the three squares and the rest of the board fades back. A draw fades the whole board.
- **Status line** says *Your turn*, *Waiting for Bob…* or *The bot is thinking…*, and screen readers announce it. The browser tab title shows *Your turn* too.
- **Keyboard:** Tab to the board, move with the arrow keys, play with Enter or Space. Each square is labelled, for example *Row 2, column 3, empty*.
- **Connection:** a dot in the header shows Live, Reconnecting or Offline. The board locks while disconnected and reconnects automatically.
- **Phones:** the board fills the screen width and the player cards collapse to fit.
- With *reduce motion* turned on in the system settings, animations are switched off.

## How it's built

| Piece | Where |
|---|---|
| Rules (win lines, turns, draws) | `games/logic.py`: pure functions, no database |
| Bot | `games/bot.py`: `choose_move(board, symbol, level)` |
| Models | `games/models.py`: `UserPresence`, `Game`, `MatchQueueEntry` ([Data models](data-models.md#games)) |
| Business logic | `games/services.py`: `PresenceService`, `GameService`, `MatchmakingService` |
| REST | `games/views.py`, mounted at `/api/games/` ([API](api.md#games--apigames)) |
| Moves in real time | `games/consumers.py`: `GameConsumer` on `ws/games/<id>/` ([API](api.md#game--wsgamesgame-idtokenaccess_token)) |
| Invites & match results | Pushed to `user_{id}` via `games/notify.py`, delivered by chat's `NotificationConsumer` |
| Frontend | `static/js/games.js` (lobby, board, invites); styles in section 10 of `static/css/style.css` |
| Tests | `games/tests/`: rules, bot (every possible game against the hard bot), services, consumers, views |

For the request flow and design decisions, see [Architecture](architecture.md#online-presence-and-games).

## Adding another game

Tic-Tac-Toe is the first game, and the parts that aren't specific to it can be reused:

- **Reuse as-is:** presence, challenges, Quick match, the notification events, the lobby's player list and the panel and URL wiring in `games.js`.
- **Write new:** the game's rules (a pure module like `logic.py`), its board and move validation, its board component in the frontend and, if you want one, a bot.
- **Suggested path:** add a `kind` field to `Game` (default `"tictactoe"`) and pass it through challenge and Quick match. Then pick the rules module and board component by `kind`. The `board` field is a plain string, so a larger game can store its own encoding, or you can add a JSON field.
