FROM registry.access.redhat.com/ubi9/python-311:latest
USER root

# Install EPEL repositories for inotify-tools
RUN rpm -ivh https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm

# Install System Dependencies
ENV DNF_OPTS="--setopt=install_weak_deps=False --setopt=tsflags=nodocs"
RUN dnf update -y && \
    dnf install -y ${DNF_OPTS} \
                python3-pip \
                inotify-tools \
 && dnf clean all -y

# Install PDM
# Use the system environment so the provided virtual environment can be re-used later
# without clashing with PDM and its dependencies
RUN /usr/bin/pip3 install --no-cache-dir pdm

USER default

# Provision the Virtual Environment
# First install all of the dependencies, not including the application itself.
# Reuses venv shipped with the ubi9/python-311 builder image.
COPY pyproject.toml pdm.lock README.md ./
RUN pdm use -if $APP_ROOT && pdm sync --prod --no-self
# Then add the application source. Doing things in this order prevents having to
# reprovision the entire virtual environment layer for source code changes.
COPY src/ src/
# TODO: allow -G groups to be configured through build args to produce image variants
RUN pdm use -if $APP_ROOT && pdm sync -G aws --prod

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["bowser"]
