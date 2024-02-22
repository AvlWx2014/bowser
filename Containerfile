FROM registry.access.redhat.com/ubi9/python-311:latest
USER root

# Install PDM
ENV DNF_OPTS="--setopt=install_weak_deps=False --setopt=tsflags=nodocs"
RUN dnf update -y && \
    dnf install -y ${DNF_OPTS} \
                python3-pip \
                inotify-tools \
 && dnf clean all -y
# Install PDM in the system environment so the provided virtual environment can be
# re-used later without clashing with PDM and its dependencies
RUN /usr/bin/pip3 install --no-cache-dir pdm

USER default

# First provision the virtual environment, reusing the one provided
# by the ubi9/python-311 base image
COPY pyproject.toml pdm.lock README.md ./
RUN pdm use -if $APP_ROOT && pdm sync --prod --no-self
# Then add the application source reusing the virtual environment provided
# by the ubi9/python-311 base image. Doing things in this order prevents having to
# reprovision the entire virtual environment layer for source code changes.
COPY src/ src/
# TODO: allow -G groups to be configured through build args to produce image variants
RUN pdm use -if $APP_ROOT && pdm sync -G aws --prod

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["bowser"]