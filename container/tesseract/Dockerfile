FROM ubuntu:22.04

# set proper locales
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

# set TESSDATA_PREFIX
ENV TESSDATA_PREFIX /usr/local/share/tessdata

ARG TESSERACT_REPOSITORY
ARG TESSERACT_REF

# set frontend non-interactive to silence interactive tzdata config
ARG DEBIAN_FRONTEND=noninteractive


# install common tools and tesseract build dependencies
# use provided leptonica
# tzdata required for proper timezone settings
RUN apt-get update && apt-get install -y \
	apt-utils \
	automake \
	g++ \
	git \
	libjpeg-dev \
	libgif-dev \
	libwebp-dev \
	libopenjp2-7-dev \
	libpng-dev \
	libtiff-dev \
	libtool \
	pkg-config \
	tzdata \
	xzgv \
	zlib1g-dev \
	libleptonica-dev \
	libpango1.0-dev \
	libicu-dev

# set proper date and timezone in container
RUN echo "Europe/Berlin" > /etc/timezone
RUN ln -sf /usr/share/zoneinfo/Europe/Berlin /etc/localtime
RUN dpkg-reconfigure -f noninteractive tzdata

# diagnostic output - check timezone settings
RUN cat /etc/timezone

# clone and checkout desired tesseract version tag
RUN git clone ${TESSERACT_REPOSITORY} build_tesseract
WORKDIR /build_tesseract
RUN git checkout ${TESSERACT_REF}

# compile
RUN ./autogen.sh && ./configure --disable-openmp --disable-shared 'CXXFLAGS=-g -O2 -fno-math-errno -Wall -Wextra -Wpedantic'
RUN LDFLAGS="-L/usr/local/lib" CFLAGS="-I/usr/local/include" make
RUN make
RUN make install && ldconfig
