ARG EXPORTER_IMAGE
FROM ${EXPORTER_IMAGE}

ARG EXPORTER_IMAGE_ID
LABEL io.m7kni.failure-harness.base-image-id=${EXPORTER_IMAGE_ID}

USER root
COPY tests/harness /app/tests/harness
RUN chown -R exporter:exporter /app/tests
USER exporter
ENTRYPOINT ["python", "-m", "tests.harness.server"]
