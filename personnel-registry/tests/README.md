# Tests

`smoke.py` runs the API end to end against a real database: it rebuilds the
schema, checks the migration matches the models, then exercises groups, custom
fields, personnel, search, CSV export, users and sessions, and finally rolls the
migration back and forward.

It is not run inside the container. Point it at a database you don't mind it
wiping:

    cd app
    pip install -r requirements.txt httpx
    SECRET_KEY=$(python3 -c "import secrets;print(secrets.token_urlsafe(40))") \
    ADMIN_PASSWORD=admin-pass-12345 \
    DB_ENGINE=postgres DB_HOST=127.0.0.1 DB_PASSWORD=... \
    python3 ../tests/smoke.py

Run it for both engines before tagging a release.
