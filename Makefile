.PHONY: demo test api ui eval install

install:
	pip install -r requirements.txt

demo:
	set INGESTION_FIXTURE_MODE=true && python -m pipeline.demo

test:
	set INGESTION_FIXTURE_MODE=true && pytest -q

api:
	uvicorn api.main:app --reload

ui:
	streamlit run ui/app.py

eval:
	python -m eval.runner
