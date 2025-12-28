IMAGE_NAME?=luismunozvillarreal/nutrition-webapp
TAG?=latest


.PHONY: docker-build docker-tag docker-push

docker-build:
	docker build . -f platform/docker/Dockerfile -t $(IMAGE_NAME):$(TAG)

docker-tag:
	docker tag $(IMAGE_NAME):$(TAG) $(IMAGE_NAME):latest

docker-push:
	docker push $(IMAGE_NAME):$(TAG)
	docker push $(IMAGE_NAME):latest

docker-build-tag-push: docker-build docker-tag docker-push
	@echo "Docker image $(IMAGE_NAME):$(TAG) built and pushed"
