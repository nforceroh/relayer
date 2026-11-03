FROM ghcr.io/nforceroh/alpine-base:3.24

ARG \
BUILD_DATE=unknown \
VERSION=unknown \
VCS_REF=unknown \
BASE_DIGEST=unknown

LABEL \
org.label-schema.maintainer="Sylvain Martin (sylvain@nforcer.com)" \
org.label-schema.build-date="${BUILD_DATE}" \
org.label-schema.version="${VERSION}" \
org.label-schema.vcs-ref="${VCS_REF}" \
org.opencontainers.image.revision="${VCS_REF}" \
org.opencontainers.image.base.digest="${BASE_DIGEST}" \
org.opencontainers.image.base.name="ghcr.io/nforceroh/alpine-base:3.24" \
org.label-schema.vcs-url="https://github.com/nforceroh/relayer" \
org.label-schema.schema-version="1.0"

ENV \
LANG=C.UTF-8 \
LC_ALL=C.UTF-8 \
TZ=America/New_York \
PUID=3001 \
PGID=3000 \
INSTALL_PATH=/data/web/relayer \
DB_HOST=mariadb \
DB_PORT=3306 \
DB_DATABASE=mail \
DB_USER=relayer \
POSTFIX_HOST=postfix \
POSTFIX_PORT=25 \
ADMIN_USER=admin

### Install Dependencies | Create relayer user
RUN apk add --no-cache --update \
python3 \
py3-pip \
&& addgroup -g ${PGID} relayer \
&& mkdir -p ${INSTALL_PATH} \
&& adduser -D -u ${PUID} -G relayer -h ${INSTALL_PATH} -s /sbin/nologin relayer

COPY requirements.txt ${INSTALL_PATH}/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r ${INSTALL_PATH}/requirements.txt \
&& rm -rf /var/cache/apk/*

### Add Files
COPY app ${INSTALL_PATH}/app
COPY wsgi.py ${INSTALL_PATH}/wsgi.py

### Services
COPY --chmod=755 content/etc/s6-overlay /etc/s6-overlay

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
CMD curl -sf http://localhost:8080/healthz || exit 1

ENTRYPOINT [ "/init" ]
