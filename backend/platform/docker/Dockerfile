FROM python:3.11.8-slim-bookworm

USER root

ENV NAME=backend

ENV TERM=xterm

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN \
  apt-get update && \
  apt-get install -y --no-install-recommends \
    # Postgresql
    libpq-dev=15.6-0+deb12u1 \
    gcc=4:12.2.0-3 \
    libc6-dev=2.36-9+deb12u7 \
    curl=7.88.1-10+deb12u5 \
    wget=1.21.3-1+b2 \
    unzip=6.0-28 \
    postgresql-client=15+248 \
    # Locales
    locales=2.36-9+deb12u4 \
    # Sudo
    sudo=1.9.13p3-1+deb12u1 \
    # Server
    nginx=1.22.1-9 \
    libnginx-mod-http-lua=1:0.10.23-1 \
    ntp=1:4.2.8p15+dfsg-2~1.2.2+dfsg1-1+deb12u1 && \
  # Clean
  apt-get purge -y --auto-remove git && \
  apt-get autoclean && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/*

# Set the locale
ENV LANG=en_GB.UTF-8
ENV LANGUAGE=en_GB.UTF-8
ENV LC_ALL=en_GB.UTF-8
RUN echo "LC_ALL=en_GB.UTF-8" >> /etc/environment
RUN echo "en_GB.UTF-8 UTF-8" >> /etc/locale.gen
RUN echo "LANG=en_GB.UTF-8" > /etc/locale.conf
RUN locale-gen en_GB.UTF-8

# Set time zone
ENV TZ=Europe/London
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Add user and group
ENV USER_NAME=$NAME
RUN useradd -ms /bin/bash $USER_NAME

# Add user to sudo group
RUN echo "$USER_NAME ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
RUN /etc/init.d/sudo restart

# Server directory
ENV SRC_DIR="/srv/www/$NAME"
RUN mkdir -p $SRC_DIR/
RUN chown $USER_NAME:$USER_NAME $SRC_DIR/
WORKDIR $SRC_DIR

# Web server config with ansible
USER root
COPY platform/docker/ansible ansible
RUN \
  apt-get update && \
  # Install ansible
  apt-get install -y --no-install-recommends \
    ansible=7.3.0+dfsg-1 && \
  # Install config
  ansible-playbook "ansible/$NAME.yml" && \
  # Uninstall ansible & clean
  apt-get purge -y ansible && \
  apt-get autoremove -y && \
  apt-get autoclean && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/* && \
  rm -rf ansible

# Add user to tty group for logging purposes
RUN usermod -a -G tty "$USER_NAME"

USER $USER_NAME

# Static dir
RUN mkdir static
RUN mkdir -p public/static

# Open server port
EXPOSE 80

# Entry point
COPY platform/docker/entrypoint.sh \
    /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Paths
ENV PATH="/home/$USER_NAME/.local/bin:$PATH"
ENV PYTHON_PATH="/home/$USER_NAME/.local/bin"

# Poetry
RUN pip install --user poetry==1.7.1

# Project deps
COPY pyproject.toml .
COPY poetry.lock .
RUN poetry install --no-root --no-directory --without dev

# Copy app
COPY manage.py .
COPY config config
COPY apps apps
