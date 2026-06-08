# Romania Crypto Signals — Panel Security

How the admin login & VIP protection work, and how to configure them safely.

## What's protected

- **VIP signals** are hidden server-side. The public `/api/stats` returns VIP signals
  as **locked teasers** (symbol + side only — NO entry / TP / SL / score). The full VIP
  data is only added to the response **after** the server verifies a valid admin session.
  This means a visitor cannot get VIP data even by reading the network tab — it never
  leaves the server unless you're authenticated.

## Admin login

- Default admin: **username `admin` / password `admin666`** (override with env vars).
- Passwords for *registered* admins are stored as **PBKDF2-HMAC-SHA256** hashes with a
  random per-user salt (200k rounds) — never plaintext.
- Login is compared in **constant time** to prevent timing attacks.
- Sessions are **stateless signed tokens** (HMAC-SHA256) stored in an
  **HttpOnly, Secure, SameSite=Strict** cookie — not readable by JS, not forgeable.
- **Brute-force protection**: max 6 failed attempts per IP per 15 min, then HTTP 429.

## Registration

Self-registration of new admins requires a secret code (`ADMIN_REGISTER_CODE`).
If that env var is not set, **registration is disabled** entirely.

## Required / recommended env vars (Railway)

```env
# Change these in production!
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin666

# Strongly recommended: a long random string. Signs session tokens.
# If not set, a random key is generated and persisted in the DB.
SECRET_KEY=pune-aici-un-string-lung-si-aleator-de-minim-32-caractere

# Optional: enables admin self-registration with this code.
ADMIN_REGISTER_CODE=cod-secret-doar-pentru-tine
```

## Security checklist before going live

1. **Change `ADMIN_PASSWORD`** from `admin666` to something strong.
2. **Set `SECRET_KEY`** to a long random value (so tokens survive restarts and can't be guessed).
3. Leave `ADMIN_REGISTER_CODE` unset unless you actually need extra admins.
4. Railway serves over HTTPS, so the Secure cookie flag works automatically.
5. The `/admin.html` page is marked `noindex` so search engines won't list it.

## Endpoints

| Method | Route           | Auth        | Purpose                              |
| ------ | --------------- | ----------- | ------------------------------------ |
| GET    | `/api/stats`    | optional    | Public stats; VIP unlocked if admin  |
| GET    | `/api/me`       | —           | Is the current session an admin?     |
| POST   | `/api/login`    | —           | Log in (rate-limited)                |
| POST   | `/api/register` | code        | Create admin (needs register code)   |
| POST   | `/api/logout`   | —           | Clear session cookie                 |
