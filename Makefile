.PHONY: run test docker-up docker-down m1-stack-up m1-stack-down

run:
	python3 run.py

test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

docker-up:
	docker compose up --build

docker-down:
	docker compose down

m1-stack-up:
	zsh deploy/m1-open-webui/start-stack.sh

m1-stack-down:
	zsh deploy/m1-open-webui/stop-stack.sh
