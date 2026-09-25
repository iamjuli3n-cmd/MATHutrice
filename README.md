# MATHutrice

MATHutrice is an LLM-based tutor that helps EPF first-year students practise mathematical tools through notions, competences and training.

## What a student sees

After signing in, a student lands on the home page and picks a module, for example *Trigonométrie*. The module page shows:

- a short description of the notion;
- a global progression bar for the module;
- the competences evaluated at EPF (those listed in Moodle);
- a quick access to training, through the **M'entraîner** button;
- progression by subtheme, for each subtheme covered by the generated exercises.

Mockup of the home page:

<img width="934" height="522" alt="Mockup of the MATHutrice home page" src="https://github.com/user-attachments/assets/faa9c372-129c-4414-9160-f5f263b10f12" />

## Running it locally

**Follow [`docs/smoke-test.md`](docs/smoke-test.md).** It is the source of truth for the commands: set up, start, and check that a fresh clone of `course-2026` runs. This section explains what those commands rely on; it does not repeat them.

- **Python:** the version pinned in [`.python-version`](.python-version) (3.14).
- **Dependencies:** installed with [uv](https://docs.astral.sh/uv/) from the committed `uv.lock`, which also installs that Python version for you. Without uv, `pip install -e .` installs from `pyproject.toml` instead.
- **Environment variables:** read from a `.env` file at the repository root, copied from [`.env.example`](.env.example). `.env` is gitignored: never commit it, and never put a real key in `.env.example`. See [Configuration](#configuration).
- **Starting it:** the application is the ASGI app `mathutrice.app:app`, served by `uvicorn` from the repository root.

Modules and training stay empty on a fresh database until notions are seeded (EPF-MDE/MATHutrice#20).

### On Windows

The smoke test is written for a POSIX shell. From PowerShell:

- If `uv` is not installed, `python -m pip install --user uv` works; then call it as `python -m uv`.
- If `uv sync` fails with `invalid peer certificate: UnknownIssuer` (antivirus or network inspecting HTTPS), set `$env:UV_NATIVE_TLS = "1"` and run it again: uv then trusts the Windows certificate store.
- There is no `.venv/bin/activate`: call `.venv\Scripts\python.exe -m uvicorn ...` by its path, since `Activate.ps1` is often blocked by the execution policy.

## Configuration

Every variable the application reads is listed, with its default, in [`.env.example`](.env.example).

| Variable | Needed | What it does |
|---|---|---|
| `LLM_API_KEY` | always | Key for the **LLM endpoint**. The application refuses to start without it (`ValueError: LLM_API_KEY missing`). |
| `LLM_BASE_URL`, `LLM_MODEL` | always (defaults to Mistral) | The OpenAI-compatible endpoint and model. Change them together with the key. |
| `SESSION_SECRET` | always | Signs the session cookie. See [the caveat below](#session_secret). |
| `DATABASE_URL` | always (defaults to SQLite) | SQLite for a local clone; PostgreSQL on a deployed environment. |
| `AUTH_MODE` | optional | `entra` (the default when unset) or `dev`. Any other value stops startup. |
| `DEV_LOGIN_KEY` | optional, `dev` only | Shared key protecting the dev sign-in page. Empty means no key. Ignored (with a warning) when `AUTH_MODE=entra`. |
| `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID` | `entra` only | Microsoft Entra ID application. |
| `REDIRECT_URL` | `entra` only | Where Entra ID sends the user back after sign-in. |
| `POST_LOGOUT_REDIRECT_URL` | `entra` only | Where Entra ID sends the user after sign-out. |

## Connexion de développement (dev sign-in)

With `AUTH_MODE=dev`, the application signs you in without an identity provider: at `/dev/login` you give an EPF email address (ending in `@epfedu.fr` or `@epf.fr`) and a role (Student, Teacher or Admin), and you are signed in as that user, with **no proof of identity**. The user does not need to exist beforehand. See `CONTEXT.md`: this is not **impersonation**, which assumes a real sign-in behind it.

In this mode, startup prints `WARNING: AUTH_MODE=dev, connexion de développement active ...`, and every page shows a red banner. The `/dev/login` routes do not exist at all when `AUTH_MODE=entra`.

`.env.example` ships with `AUTH_MODE=dev`, so a fresh clone runs with no Entra credentials. **It must never be used in production.**

If `DEV_LOGIN_KEY` is set, the sign-in form asks for it, and a wrong key gets `401`.

### `SESSION_SECRET`

Whoever knows `SESSION_SECRET` can forge a session cookie for any user and role. The value in `.env.example` is a public placeholder: with it, anyone can skip `DEV_LOGIN_KEY` (and, with `AUTH_MODE=entra`, Entra ID itself) by signing their own cookie. On any environment other people can reach, replace it with a random secret, for example:

```sh
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Scripted sign-in with `curl`

`POST /dev/login` takes the same form fields as the page: `email`, `role` (`student`, `teacher` or `admin`), optionally `name`, and `key` when `DEV_LOGIN_KEY` is set. Keep the session cookie in a file and send it back on each request:

```sh
# Sign in, storing the session cookie in cookies.txt
curl -s -c cookies.txt -o /dev/null -w "%{http_code}\n" \
  -d 'email=jane.doe@epfedu.fr' -d 'role=student' \
  http://localhost:8000/dev/login        # 303: signed in
# add  -d "key=$DEV_LOGIN_KEY"  if a key is set

# Reuse the cookie on later requests
curl -s -b cookies.txt -o /dev/null -w "%{http_code}\n" \
  http://localhost:8000/                 # 200 (without the cookie: 307 to sign-in)
```

A non-EPF address gets `403`. The session lasts one hour.

## Deployment checklist

Before an environment is reachable by students:

- [ ] `AUTH_MODE` unset, or `entra`.
- [ ] `CLIENT_ID`, `CLIENT_SECRET`, `TENANT_ID`, `REDIRECT_URL` and `POST_LOGOUT_REDIRECT_URL` set for that environment.
- [ ] `SESSION_SECRET` set to a random secret, not the placeholder from `.env.example`.
- [ ] `LLM_API_KEY` provided by the environment, never committed.
- [ ] `DATABASE_URL` pointing at PostgreSQL.
- [ ] [`docs/smoke-test.md`](docs/smoke-test.md) run on the Linux host you deploy to.

## Where to read next

- [`CONTEXT.md`](CONTEXT.md): the project's vocabulary (authentication modes, LLM endpoint…).
- [`mathutrice/README.md`](mathutrice/README.md): package conventions and the boundary rule checked by `tach`.
- [`docs/adr/`](docs/adr/): architecture decision records.

## Licence

MIT, see [`LICENSE`](LICENSE).
