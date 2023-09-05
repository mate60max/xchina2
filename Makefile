all: xchina2

clean:
	rm -rf build/ dist/ xchina2.tar.gz *.dump *.part* *.ytdl *.info.json *.mp4 *.m4a *.flv *.mp3 *.avi *.mkv *.webm *.3gp *.wav *.ape *.swf *.jpg *.png CONTRIBUTING.md.tmp xchina2 xchina2.exe
	find xc2 -name "*.pyc" -delete
	find xc2 -name "*.class" -delete

PREFIX ?= /usr/local
BINDIR ?= $(PREFIX)/bin
MANDIR ?= $(PREFIX)/man
SHAREDIR ?= $(PREFIX)/share
PYTHON ?= /usr/bin/env python3

install: xchina2
	install -d $(DESTDIR)$(BINDIR)
	install -m 755 xchina2 $(DESTDIR)$(BINDIR)

.PHONY: all clean install

xchina2: xc2/*.py
	mkdir -p zip
	for d in xc2 ; do \
	  mkdir -p zip/$$d ;\
	  cp -pPR $$d/*.py zip/$$d/ ;\
	done
	touch -t 200001010101 zip/xc2/*.py
	mv zip/xc2/__main__.py zip/
	cd zip ; zip -q ../xchina2 xc2/*.py __main__.py
	rm -rf zip
	echo '#!$(PYTHON)' > xchina2
	cat xchina2.zip >> xchina2
	rm xchina2.zip
	chmod a+x xchina2