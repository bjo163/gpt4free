FROM selenium/node-chrome

ARG G4F_VERSION=0.5.2.4
ENV G4F_VERSION $G4F_VERSION

ENV SE_SCREEN_WIDTH 1850
ENV G4F_DIR /app
ENV G4F_LOGIN_URL http://localhost:7900/?autoconnect=1&resize=scale&password=secret

USER root

#  If docker compose, install git
RUN if [ "$G4F_VERSION" = "" ] ; then \
  apt-get -qqy update && \
  apt-get -qqy install git \
  ; fi

# Install Python3, pip, remove OpenJDK 11, clean up
RUN apt-get -qqy update \
  && apt-get -qqy upgrade \
  && apt-get -qyy autoremove \
  && apt-get -qqy install python3 python-is-python3 pip \
  && apt-get -qyy remove openjdk-11-jre-headless \
  && apt-get -qyy autoremove \
  && apt-get -qyy clean \
  && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Update entrypoint
COPY docker/supervisor.conf /etc/supervisor/conf.d/selenium.conf
COPY docker/supervisor-api.conf /etc/supervisor/conf.d/api.conf

# Change background image
COPY docker/background.png /usr/share/images/fluxbox/ubuntu-light.png

# Add user, fix permissions for $HOME/.local
RUN chown "${SEL_UID}:${SEL_GID}" $HOME/.local

# Set the working directory in the container.
WORKDIR $G4F_DIR

# Copy the project's requirements file into the container.
COPY requirements.txt $G4F_DIR

# Upgrade pip for the latest features and install the project's Python dependencies.
RUN pip install --break-system-packages --upgrade pip \
  && pip install --break-system-packages -r requirements.txt

# Create directories for volumes and ensure the runtime user ($SEL_UID) owns them.
# This must be done as root before switching to USER $SEL_UID.
# This ensures that when named volumes (like har_and_cookies, generated_media, and gpt4free_data for /app)
# are initialized from the image content, they get the correct ownership.
RUN mkdir -p $G4F_DIR/har_and_cookies $G4F_DIR/generated_media $G4F_DIR/g4f && \
    chown -R "${SEL_UID}:${SEL_GID}" $G4F_DIR

USER $SEL_UID

# Copy the entire package into the container.
# The --chown flag is still good practice, though $G4F_DIR and its subdirectories
# (including $G4F_DIR/g4f if created by the chown command above) are now owned by $SEL_UID.
ADD --chown=$SEL_UID:$SEL_GID g4f $G4F_DIR/g4f

# Expose ports
EXPOSE 8080 7900
