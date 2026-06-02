# ChatRooms — Roadmap

## End-to-End Encryption

> **Goal:** The server stores only ciphertext and never sees message content.
> Messages are encrypted on the sender's device and decrypted only on recipients' devices.

### Approach

| Layer | Technology |
|-------|-----------|
| Message encryption | AES-GCM 256-bit (per-room symmetric key) |
| Key exchange | RSA-OAEP 2048-bit (per-user asymmetric key pair) |
| Crypto API | Browser-native `window.crypto.subtle` (no external library) |
| Private key storage | Browser IndexedDB (non-extractable, never leaves device) |
| Public key storage | Server — `User.rsa_public_key` field |
| Room key storage | Server — `RoomMembership.encrypted_room_key` field (wrapped per user) |

---

### Phase 1 — Backend Models

- [ ] Add `User.rsa_public_key` (TextField) — stores RSA public key as JWK JSON string
- [ ] Add `RoomMembership.encrypted_room_key` (TextField) — stores AES room key wrapped with user's RSA public key, base64-encoded
- [ ] Add `Message.is_encrypted` (BooleanField, default `False`) — flags encrypted messages so JS doesn't need content heuristics
- [ ] Write migrations (`accounts/0002`, `chat/0004`) — non-destructive, all fields have defaults

---

### Phase 2 — New API Endpoints

- [ ] `PATCH /api/auth/me/keys/` — user uploads their RSA public key after generation
- [ ] `GET /api/auth/users/<username>/public-key/` — fetch another user's RSA public key for key wrapping
- [ ] `GET /api/rooms/<slug>/my-key/` — returns this user's encrypted room key (`has_key: true/false`)
- [ ] `POST /api/rooms/<slug>/distribute-key/` — store encrypted room key for a target member (idempotent)
- [ ] `GET /api/rooms/<slug>/members-without-key/` — list members missing a room key, with their public keys

---

### Phase 3 — `static/js/crypto.js` (new file)

- [ ] RSA key pair generation (`generateRsaKeyPair`) and IndexedDB persistence (`storePrivateKey` / `loadPrivateKey`)
- [ ] Public key export/import as JWK (`exportPublicKeyJwk` / `importPublicKeyJwk`)
- [ ] AES room key generation (`generateAesKey`), wrapping (`wrapAesKey`), unwrapping (`unwrapAesKey`)
- [ ] Room key IndexedDB persistence — stored as raw bytes, re-imported on load (`storeRoomKey` / `loadRoomKey`)
- [ ] Per-message encryption (`encryptMessage`) — 12-byte random IV per message, format `<b64iv>.<b64ciphertext>`
- [ ] Per-message decryption (`decryptMessage`) — returns `null` on any failure (no throws exposed to caller)
- [ ] Bootstrap function (`cryptoBootstrap`) — drives the full key-loading sequence, returns `{ ready, reason }`

---

### Phase 4 — `room.js` Changes

- [ ] `_initCrypto()` — new async method called in constructor; handles all key-loading states before enabling input
- [ ] `_sendText()` — encrypt with room AES key before `ws.send`; cache key as `this._aesKey` to avoid per-message IDB reads
- [ ] `_appendMessage()` — becomes `async`; decrypts when `data.is_encrypted`, renders legacy plaintext when `false`
- [ ] `_loadHistory()` — uses `Promise.all` for concurrent async decryption of history messages
- [ ] `_pollForKey()` — polls `GET /my-key/` every 15 s (stops after 3 min or on success)
- [ ] `_requestKeyDistribution()` — sends `{"type":"key_request"}` via WebSocket + starts polling
- [ ] `_handleKeyRequest(msg)` — fetches requester's public key, wraps own room key, POSTs to `distribute-key`
- [ ] `_distributePendingKeys()` — called on WS open; distributes room key to all members-without-key who have a public key
- [ ] `destroy()` — clear `_keyPollTimer` on cleanup

---

### Phase 5 — `consumers.py` Changes

- [ ] Text branch — pass `content` through opaque; always save and broadcast with `is_encrypted: true`
- [ ] New `key_request` branch — broadcast `key_request_event` to all group members except the sender
- [ ] `MessageService.create_text()` — add `is_encrypted` param
- [ ] `MessageSerializer` — expose `is_encrypted` field
- [ ] `DashboardRoomSerializer.get_last_message()` — return `content: null` when `is_encrypted=True` (prevents ciphertext leaking into sidebar)
- [ ] `dashboard.js` `renderRoomItem()` — show `[Encrypted message]` when `content` is null

---

### Key Distribution Flows

#### New room creator
```
Bootstrap → no room key → is_creator
  → generate AES key
  → wrap for self → POST distribute-key
  → cryptoReady = true ✓
```

#### New member joins (online distributor available)
```
Join room → bootstrap → no room key
  → send key_request via WebSocket
  → online member: fetch requester's public key → wrap room key → POST distribute-key
  → poll picks up within 15 s → unwrap → cryptoReady = true ✓
```

#### New member joins (no one online)
```
Same start → poll for 3 min → times out
  → next member to open room calls _distributePendingKeys()
  → member gets key on next poll tick → cryptoReady = true ✓
```

---

### Graceful Degradation

| State | Behaviour |
|-------|-----------|
| No private key in IDB (new device / cleared storage) | Generate new keys, upload public key, request distribution; input disabled |
| Private key present, no room key yet | Poll every 15 s; input disabled; system message shown |
| Decryption fails on a single message | Render `[Could not decrypt]` inline; other messages unaffected |
| `crypto.subtle` unavailable (non-HTTPS) | Persistent error banner; app otherwise functional |
| Legacy plaintext messages (pre-migration) | `is_encrypted: false` → rendered as-is; fully backward-compatible |

---

### Verification Checklist

- [ ] Sent messages are stored as ciphertext in DB (`SELECT content FROM chat_message LIMIT 1`)
- [ ] Second account in same room: messages decrypt and display correctly
- [ ] Third account joins: key distribution flow completes, messages become readable
- [ ] Django admin Messages list: `content` column shows ciphertext, not plaintext
- [ ] Sidebar preview shows `[Encrypted message]` instead of ciphertext
- [ ] Legacy plaintext messages (created before migration) still display correctly
- [ ] Clear IndexedDB in browser devtools → key regeneration + redistribution flow works end-to-end

---

### Out of Scope (MVP)

- Image and voice message encryption (files stored server-side as-is)
- Key rotation when a member leaves a room
- Multi-device private key sync
- Forward secrecy
