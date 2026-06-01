.PHONY: doctor-frontend-volume test-atlas-live-docker-local-llm

doctor-frontend-volume:
	cd frontend && npm run doctor:frontend-volume

test-atlas-live-docker-local-llm:
	cd frontend && npm run test:e2e:atlas:docker:local-llm
