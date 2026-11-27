# Baseline

- Upstream: https://github.com/ConsciousUniverse/simple-stock-management
- Licence: GPLv3
- Pinned commit: ce90315b6e243103487465fb2b26ac91de55e7a7
- Install: py -m pipenv install --dev ; copy .env_default .env (set LOG_FILE='ssm.log')
- Migrate: py -m pipenv run python manage.py migrate
- Start: py -m pipenv run python manage.py runserver
- Seed and reset: py -m pipenv run python scripts\reset_and_seed.py
- Test users: manager, shop1, shop2 (password test-pass-123)
- Team tests: py -m pipenv run python -m pytest tests/team -q