# =========================
# STAGE 1 — Base builder with root
# =========================
FROM selenium/node-chrome AS builder

ARG G4F_VERSION
ENV G4F_VERSION $G4F_VERSION
ENV G4F_DIR /app

USER root

# Install OS and Python dependencies
RUN apt-get -qqy update && \
    apt-get -qqy install git python3 python-is-python3 python3-pip && \
    apt-get -qyy remove openjdk-11-jre-headless && \
    apt-get -qyy autoremove && \
    apt-get -qyy clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Copy only requirements to leverage Docker cache
WORKDIR $G4F_DIR
COPY requirements.txt .

# Upgrade pip and install Python dependencies into /install directory
RUN pip install --upgrade pip && \
    pip install --prefix=/install -r requirements.txt

# =========================
# STAGE 2 — Runtime container
# =========================
FROM selenium/node-chrome

ENV SE_SCREEN_WIDTH 1850
ENV G4F_DIR /app
ENV G4F_LOGIN_URL http://localhost:7900/?autoconnect=1&resize=scale&password=secret

# Switch to root to apply changes
USER root

# Supervisor & background
COPY docker/supervisor.conf /etc/supervisor/conf.d/selenium.conf
COPY docker/supervisor-api.conf /etc/supervisor/conf.d/api.conf
COPY docker/background.png /usr/share/images/fluxbox/ubuntu-light.png

# Copy only installed python dependencies from stage 1
COPY --from=builder /install /usr/local

# Set working directory
WORKDIR $G4F_DIR

# Copy app code
COPY --chown=$SEL_UID:$SEL_GID g4f ./g4f

# Copy config (if needed)
COPY requirements.txt .

# Fix permission on $HOME/.local (used by pip cache/tools)
RUN chown -R "${SEL_UID}:${SEL_GID}" $HOME/.local $G4F_DIR

# Switch to non-root user
USER $SEL_UID

# Expose ports
EXPOSE 8080 7900
