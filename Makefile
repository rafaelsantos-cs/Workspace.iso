.PHONY: validate prepare iso container clean

validate:
	./scripts/validate.sh

prepare:
	./scripts/prepare-profile.sh

iso:
	sudo ./scripts/build-iso.sh

container:
	./scripts/build-in-container.sh

clean:
	./scripts/clean.sh
