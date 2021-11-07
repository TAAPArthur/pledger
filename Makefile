all: test
test:
	python -m unittest -b -f unit_tests.py

install:
	install -D pledger.py $(DESTDIR)/usr/bin/pledger
