# =========================
# STAGE 1 — Builder
# =========================
FROM selenium/node-chrome AS builder

# Set default version
ARG G4F_VERSION=0.5.2.4
ENV G4F_VERSION=$G4F_VERSION
ENV G4F_DIR=/app

USER root

# Install OS and Python dependencies
RUN apt-get -qqy update && \
    apt-get -qqy install git python3 python-is-python3 python3-pip && \
    apt-get -qyy remove openjdk-11-jre-headless && \
    apt-get -qyy autoremove && \
    apt-get -qyy clean && \
    rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Set working directory
WORKDIR $G4F_DIR

# Copy only requirements to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies into isolated install directory
RUN pip install --upgrade pip && \
    pip install --prefix=/install -r requirements.txt

# =========================
# STAGE 2 — Runtime
# =========================
FROM selenium/node-chrome

# Set environment variables
ENV SE_SCREEN_WIDTH=1850
ENV G4F_VERSION=0.5.2.4
ENV G4F_DIR=/app
ENV G4F_LOGIN_URL=http://localhost:7900/?autoconnect=1&resize=scale&password=secret

# Switch to root to apply customizations
USER root

# Supervisor & Background Setup
COPY docker/supervisor.conf /etc/supervisor/conf.d/selenium.conf
COPY docker/supervisor-api.conf /etc/supervisor/conf.d/api.conf
COPY docker/background.png /usr/share/images/fluxbox/ubuntu-light.png

# Copy dependencies from builder stage
COPY --from=builder /install /usr/local

# Set workdir and copy source
WORKDIR $G4F_DIR
COPY --chown=$SEL_UID:$SEL_GID g4f ./g4f
COPY requirements.txt .

# Fix permission for non-root usage
RUN chown -R "${SEL_UID}:${SEL_GID}" $HOME/.local $G4F_DIR

# Switch to non-root user for safety
USER $SEL_UID

# Expose necessary ports
EXPOSE 8080 7900
