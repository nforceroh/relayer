# Local build and test only — CI is the sole publisher.
# Shared pipelines: https://github.com/nforceroh/.github
SHELL := /bin/bash
IMAGE ?= ghcr.io/nforceroh/relayer
TAG   ?= dev

.PHONY: build test run

build:
	docker build \
		--build-arg BUILD_DATE="$(shell date -u +'%Y-%m-%dT%H:%M:%SZ')" \
		--build-arg VERSION="$(TAG)" \
		--tag $(IMAGE):$(TAG) .

test: build
	python -m unittest discover -s tests -t . -v

run: build
	docker run --rm -it \
		-p 8080:8080 \
		$(IMAGE):$(TAG)
