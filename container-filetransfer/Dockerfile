FROM python:alpine3.7

MAINTAINER Stewart Adam "stad@microsoft.com"

#
## Setup Python dependencies
#
ADD requirements.txt /root/

# Setup build deps for cryptography and cffi
RUN set -e; \
  apk update && \
  apk --no-cache add --virtual .build-deps build-base python3-dev musl-dev libffi-dev openssl-dev git && \
  pip install -U pip && \
  pip install --no-cache-dir -r /root/requirements.txt && \
  apk del .build-deps

# Add main Python script
ADD cloud-transfer.py /home/ft/

#
## Setup runtime environment
#
WORKDIR /home/ft

# Setup non-root user
RUN addgroup -g 987 ft && \
    adduser -D -u 987 -G ft ft
USER ft

# Container execution
ENTRYPOINT ["/usr/local/bin/python", "cloud-transfer.py"]
CMD ["--help"]
