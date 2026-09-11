# Oakwood Life Center

A small Flask web app for collecting personal and education details in an external MongoDB database.

## Run locally

1. Create a MongoDB Atlas cluster or use another hosted MongoDB provider.
2. Create a virtual environment and install dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

3. Set environment variables. Copy `.env.example` to `.env` and replace both values. Do not commit `.env`.

```powershell
$env:SECRET_KEY = 'use-a-long-random-secret'
$env:MONGO_URI = 'mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority'
$env:MONGO_DB_NAME = 'learner_vault'
$env:FLASK_ENV = 'development'
```

4. Start the app:

```powershell
py app.py
```

Open `http://127.0.0.1:5000`.

## Security notes

- Passwords are never stored directly. Werkzeug stores salted, slow password hashes and verifies them with `check_password_hash`.
- User accounts and profiles are stored as MongoDB documents in the external database.
- Every profile request requires a signed-in session and uses `current_user.profile`; users cannot provide an arbitrary user ID.
- Use HTTPS in production and set `FLASK_ENV=production` so the session cookie is marked Secure.
- Use a managed MongoDB provider with TLS, encrypted storage, backups, restricted credentials, and least-privilege database access.
- This starter includes CSRF tokens but does not implement email verification, password reset, rate limiting, audit logs, or application-level field encryption yet. Add those before handling real sensitive data.
- Do not put real credentials in source control.
