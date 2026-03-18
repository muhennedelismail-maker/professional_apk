.PHONY: run test docker-up docker-down

run:
	python3 run.py

test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

docker-up:
	docker compose up --build

docker-down:
	docker compose down
