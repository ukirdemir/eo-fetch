# eo-fetch in a container: one command-line tool for Earth-observation and climate data.
#
#   docker build -t eo-fetch .
#   docker run --rm eo-fetch providers
#   docker run --rm -v "%cd%\data:/data" eo-fetch download --provider dwd ... --dest /data/dwd
#
# Credentials are never baked into the image: mount your credential files or pass environment
# variables when you run it (see the README, "Docker").

FROM python:3.12-slim

# Build with --build-arg EXTRAS=eumetsat,nasa for a smaller image.
ARG EXTRAS=all

ENV PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    MPLBACKEND=Agg \
    HOME=/home/eo

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --home-dir /home/eo --uid 1000 eo \
    && mkdir /data && chown eo /data

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[${EXTRAS}]"

USER eo
WORKDIR /data
VOLUME /data
ENTRYPOINT ["eo-fetch"]
CMD ["--help"]
