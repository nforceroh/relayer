FROM ghcr.io/nforceroh/k8s-alpine-baseimage:3.24

ARG \
BUILD_DATE=unknown \
VERSION=unknown

LABEL \
org.label-schema.maintainer="Sylvain Martin (sylvain@nforcer.com)" \
org.label-schema.build-date="${BUILD_DATE}" \
org.label-schema.version="${VERSION}" \
org.label-schema.vcs-url="https://github.com/nforceroh/k8s-relayer" \
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

# Create the relayer user. Note: unlike PUID/PGID env vars that some
# LinuxServer-style images reconcile at container start via a cont-init
# script, this Dockerfile bakes the uid/gid in at build time -- if your
# other images dynamically chown/re-map PUID/PGID at runtime and you want
# the same here, add a matching cont-init.d script; not included here to
# keep this image's footprint minimal.
RUN \
echo "Add relayer user" \
&& addgroup -g ${PGID} relayer \
&& adduser -D -u ${PUID} -G relayer -h ${INSTALL_PATH} -s /sbin/nologin relayer

# python3/py3-pip only -- Flask, PyMySQL, and gunicorn are all pure Python,
# so no compiler/musl-dev is needed.
RUN apk add --no-cache --update \
python3 \
py3-pip \
&& mkdir -p ${INSTALL_PATH}

COPY requirements.txt ${INSTALL_PATH}/requirements.txt
RUN pip install --no-cache-dir --break-system-packages -r ${INSTALL_PATH}/requirements.txt \
&& rm -rf /var/cache/apk/*

COPY app ${INSTALL_PATH}/app
COPY wsgi.py ${INSTALL_PATH}/wsgi.py
RUN chown -R relayer:relayer ${INSTALL_PATH}

# s6 service definition -- starts gunicorn as the relayer user under s6,
# same pattern as the Dovecot/ViMbAdmin images built on this base image.
COPY --chmod=755 content/etc/s6-overlay /etc/s6-overlay

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
CMD curl -sf http://localhost:8080/healthz || exit 1

ENTRYPOINT [ "/init" ]
