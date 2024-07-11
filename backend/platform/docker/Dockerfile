FROM debian:trixie-20240423-slim

USER root

ENV NAME=backend

ENV TERM=xterm

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN \
  apt-get update && \
  apt-get install -y --no-install-recommends \
    # Postgresql
    libpq-dev=16.3-1+b1 \
    gcc=4:13.2.0-7 \
    libc6-dev=2.38-14 \
    postgresql-client=16+261 \
    # Locales
    locales=2.38-14 \
    # Sudo
    sudo=1.9.15p5-3+b1 \
    # Server
    nginx=1.26.0-1 \
    libnginx-mod-http-lua=1:0.10.26-3 \
    python-is-python3=3.11.4-1 \
    python3-dev=3.12.3-1 \
    python3-poetry=1.8.3+dfsg-2 \
    ntp=1:4.2.8p15+dfsg-2~1.2.3+dfsg1-3 && \
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
    ansible=10.1.0+dfsg-1 && \
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
ENV PYTHONPATH="/home/$USER_NAME/.local/bin:$SRC_DIR/.venv/lib/python3.11/site-packages/"

# Project deps
COPY pyproject.toml .
COPY poetry.lock .
RUN poetry config virtualenvs.in-project true
RUN poetry install --no-root --no-directory --without dev

# Copy app
COPY manage.py .
COPY config config
COPY apps apps
