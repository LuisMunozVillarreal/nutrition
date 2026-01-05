IMAGE_NAME := luismunozvillarreal/nutrition-backend
TAG := latest

.PHONY: install pytest bandit flake8 black mypy pylint pylint-tests pydocstyle pydocstyle-tests docker-build docker-tag docker-push restore-db migrations-check migrate ci-migrations

install:
	uv sync

pre-commit: pytest bandit flake8 black-fix mypy pylint pylint-tests pydocstyle pydocstyle-tests

pytest:
	uv run pytest -n 4 $(ARGS)

bandit:
	uv run bandit -c pyproject.toml -r manage.py config apps tests $(ARGS)

flake8:
	uv run flake8 --tee --count manage.py config apps tests $(ARGS)

black:
	uv run black --check manage.py config apps tests $(ARGS)

black-fix:
	uv run black manage.py config apps tests $(ARGS)

mypy:
	uv run mypy --disallow-untyped-defs --exclude migrations manage.py config apps $(ARGS)

pylint:
	uv run pylint -j 4 config apps $(ARGS)

pylint-tests:
	uv run pylint -j 4 --rcfile .pylintrc-tests tests $(ARGS)

pydocstyle:
	uv run pydocstyle config apps --count --add-select D401 $(ARGS)

pydocstyle-tests:
	uv run pydocstyle tests --count $(ARGS)

docker-build:
	docker build . -f platform/docker/Dockerfile -t $(IMAGE_NAME):$(TAG)

docker-tag:
	docker tag $(IMAGE_NAME):$(TAG) $(IMAGE_NAME):latest

docker-push:
	docker push $(IMAGE_NAME):$(TAG)
	docker push $(IMAGE_NAME):latest

restore-db:
	uv run ./manage.py dbrestore --noinput -d nutrition

migrations-check:
	uv run ./manage.py makemigrations --check

migrate:
	uv run ./manage.py migrate

start-server:
	uv run ./manage.py runserver 0:8000
