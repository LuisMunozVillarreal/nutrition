IMAGE_NAME?=luismunozvillarreal/nutrition-backend
TAG?=latest
DJANGO_SETTINGS_MODULE?=config.settings
SECRET_KEY?=insecure-local-test-secret
GEMINI_API_KEY?=local-test-gemini-key
DATABASE_URL?=sqlite:///db.sqlite3
PYTEST_WORKERS?=4

.PHONY: install agent-bootstrap agent-test-focused agent-pytest agent-verify python-checks pytest bandit flake8 black black-fix mypy pylint pylint-tests pydocstyle pydocstyle-tests docker-build docker-tag docker-push docker-build-contract-tag-push restore-db reset-db migrations-check migrate ci-migrations chart-contract-test docker-contract-test contract-tests

install:
	uv sync

agent-bootstrap:
	uv sync --frozen

agent-test-focused: override export DJANGO_SETTINGS_MODULE := $(value DJANGO_SETTINGS_MODULE)
agent-test-focused: override export SECRET_KEY := $(value SECRET_KEY)
agent-test-focused: override export GEMINI_API_KEY := $(value GEMINI_API_KEY)
agent-test-focused: override export DATABASE_URL := $(value DATABASE_URL)
agent-test-focused: override export TEST := $(value TEST)
agent-test-focused:
	@test -n "$$TEST" || (echo "TEST=<pytest target> is required" >&2; exit 2)
	env -u PYTEST_ADDOPTS uv run pytest --no-cov -n 2 -- "$$TEST"

agent-pytest: override export DJANGO_SETTINGS_MODULE := $(value DJANGO_SETTINGS_MODULE)
agent-pytest: override export SECRET_KEY := $(value SECRET_KEY)
agent-pytest: override export GEMINI_API_KEY := $(value GEMINI_API_KEY)
agent-pytest: override export DATABASE_URL := $(value DATABASE_URL)
agent-pytest:
	env -u PYTEST_ADDOPTS -u COVERAGE_RCFILE -u COVERAGE_FILE \
	-u COVERAGE_PROCESS_START -u COVERAGE_FORCE_CONFIG uv run pytest -n 2 \
	--cov-config=pyproject.toml --cov-fail-under=100 tests ../.circleci/scripts

agent-verify: override ARGS=
agent-verify: override export DJANGO_SETTINGS_MODULE := $(value DJANGO_SETTINGS_MODULE)
agent-verify: override export SECRET_KEY := $(value SECRET_KEY)
agent-verify: override export GEMINI_API_KEY := $(value GEMINI_API_KEY)
agent-verify: override export DATABASE_URL := $(value DATABASE_URL)
agent-verify: agent-pytest bandit flake8 black mypy pylint pylint-tests pydocstyle pydocstyle-tests

python-checks: pytest bandit flake8 black-fix mypy pylint pylint-tests pydocstyle pydocstyle-tests

pytest:
	DJANGO_SETTINGS_MODULE=$(DJANGO_SETTINGS_MODULE) \
	SECRET_KEY=$(SECRET_KEY) \
	GEMINI_API_KEY=$(GEMINI_API_KEY) \
	DATABASE_URL=$(DATABASE_URL) \
	uv run pytest -n $(PYTEST_WORKERS) tests ../.circleci/scripts $(ARGS)

bandit:
	uv run bandit -c pyproject.toml -r manage.py config apps ../.circleci/scripts $(ARGS)

flake8:
	uv run flake8 --tee --count manage.py config apps tests ../.circleci/scripts $(ARGS)

black:
	uv run black --config pyproject.toml --check manage.py config apps tests ../.circleci/scripts $(ARGS)

black-fix:
	uv run black --config pyproject.toml manage.py config apps tests ../.circleci/scripts $(ARGS)

mypy:
	uv run mypy --disallow-untyped-defs manage.py config apps ../.circleci/scripts $(ARGS)

pylint:
	uv run pylint -j 4 config apps ../.circleci/scripts $(ARGS)

pylint-tests:
	uv run pylint -j 4 --rcfile .pylintrc-tests tests ../.circleci/scripts $(ARGS)

pydocstyle:
	uv run pydocstyle config apps ../.circleci/scripts --count --add-select D401 $(ARGS)

pydocstyle-tests:
	uv run pydocstyle tests ../.circleci/scripts --count $(ARGS)

docker-build:
	docker build . -f platform/docker/Dockerfile -t $(IMAGE_NAME):$(TAG)

docker-tag:
	docker tag $(IMAGE_NAME):$(TAG) $(IMAGE_NAME):latest

docker-push:
	docker push $(IMAGE_NAME):$(TAG)
	docker push $(IMAGE_NAME):latest

docker-build-tag-push: docker-build docker-tag docker-push

docker-build-contract-tag-push:
	IMAGE_NAME=$(IMAGE_NAME) TAG=$(TAG) IMAGE_TAG=$(TAG) $(MAKE) docker-build
	IMAGE_NAME=$(IMAGE_NAME) IMAGE_TAG=$(TAG) SKIP_IMAGE_BUILD=1 PRESERVE_IMAGE=1 $(MAKE) docker-contract-test
	IMAGE_NAME=$(IMAGE_NAME) TAG=$(TAG) $(MAKE) docker-tag docker-push

chart-contract-test:
	./platform/kube/tests/chart-contract-test.sh

docker-contract-test:
	./platform/docker/tests/docker-contract-test.sh

contract-tests: chart-contract-test docker-contract-test

restore-db:
	uv run ./manage.py dbrestore --noinput -d nutrition

reset-db:
	uv run ./manage.py reset_db --noinput

migrations-check:
	uv run ./manage.py makemigrations --check

migrate:
	uv run ./manage.py migrate

start-server:
	uv run ./manage.py runserver 0:8000

add-testing-user:
	uv run ./manage.py shell -c "from apps.users.models import User; import datetime; User.objects.filter(email='user@example.com').delete(); User.objects.create_user(email='user@example.com', password='password123', first_name='Nutrition', last_name='User', date_of_birth=datetime.date(1990, 1, 1), height=180.0)"
