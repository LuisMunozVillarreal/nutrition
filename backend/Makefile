IMAGE_NAME?=luismunozvillarreal/nutrition-backend
TAG?=latest

.PHONY: install python-checks pytest bandit flake8 black mypy pylint pylint-tests pydocstyle pydocstyle-tests docker-build docker-tag docker-push restore-db migrations-check migrate ci-migrations

install:
	uv sync

python-checks: pytest bandit flake8 black-fix mypy pylint pylint-tests pydocstyle pydocstyle-tests

pytest:
	uv run pytest tests ../.circleci/scripts $(ARGS)

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

restore-db:
	uv run ./manage.py dbrestore --noinput -d nutrition

migrations-check:
	uv run ./manage.py makemigrations --check

migrate:
	uv run ./manage.py migrate

start-server:
	uv run ./manage.py runserver 0:8000
