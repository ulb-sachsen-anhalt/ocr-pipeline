FROM ubuntu:18.04

# set proper locales
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

ENV TESSDATA_DIR /usr/local/share/tessdata

ARG TESSERACT_REPOSITORY
ARG TESSERACT_RELEASE

# set frontend non-interactive to silence interactive tzdata config
ARG DEBIAN_FRONTEND=noninteractive


# install common tools and tesseract build dependencies
# use provided leptonica
# tzdata required for proper timezone settings
RUN apt-get update && apt-get install -y \
	apt-utils \
	autoconf \
	autoconf-archive \
	automake \
	build-essential \
	checkinstall \
	cmake \
	g++ \
	git \
	libcairo2-dev \
	libicu-dev \
	libjpeg-dev \
	libpango1.0-dev \
	libgif-dev \
	libwebp-dev \
	libopenjp2-7-dev \
	libpng-dev \
	libtiff-dev \
	libtool \
	pkg-config \
	software-properties-common \
	tzdata \
	vim \
	wget \
	xzgv \
	zlib1g-dev \
	libleptonica-dev



# set proper date and timezone in container
RUN echo "Europe/Berlin" > /etc/timezone
RUN ln -sf /usr/share/zoneinfo/Europe/Berlin /etc/localtime
RUN dpkg-reconfigure -f noninteractive tzdata

# diagnostic output - check timezone settings
RUN cat /etc/timezone

# clone and checkout desired tesseract version tag
RUN git clone ${TESSERACT_REPOSITORY} build_tesseract
WORKDIR /build_tesseract
RUN git checkout ${TESSERACT_RELEASE}

# compile
RUN ./autogen.sh && ./configure
RUN LDFLAGS="-L/usr/local/lib" CFLAGS="-I/usr/local/include" make
RUN make
RUN make install && ldconfig

# diagnostic output - check tesseract version
RUN tesseract --version

# create tessdata dir
RUN ["mkdir", "-p", "${TESSDATA_DIR}"]

# set default tesseract data-dir as workingdir
WORKDIR ${TESSDATA_DIR}

# gather tesseract models: deutsch + deutsch fraktura + fraktura common
RUN ["wget", "-q", "https://github.com/tesseract-ocr/tessdata/raw/master/eng.traineddata"]
RUN ["wget", "-q", "https://github.com/tesseract-ocr/tessdata/raw/master/deu.traineddata"]
RUN ["wget", "-q", "https://github.com/tesseract-ocr/tessdata_best/raw/master/frk.traineddata"]
RUN ["wget", "-q", "https://github.com/tesseract-ocr/tessdata_best/raw/master/script/Fraktur.traineddata"]
RUN ["wget", "-q", "https://ub-backup.bib.uni-mannheim.de/~stweil/ocrd-train/data/Fraktur_5000000/Fraktur_5000000_0.466.traineddata", "-O", "gt4hist_5000k.traineddata"]

# diagnostic output - check languages
RUN ["tesseract", "--list-langs"]
