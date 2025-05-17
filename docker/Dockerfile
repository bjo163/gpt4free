FROM selenium/node-chrome

ARG G4F_VERSION
ENV G4F_VERSION $G4F_VERSION

ENV SE_SCREEN_WIDTH 1850
ENV G4F_DIR /app
ENV G4F_LOGIN_URL http://localhost:7900/?autoconnect=1&resize=scale&password=secret

USER root

# Jika menggunakan docker-compose: install git
RUN if [ "$G4F_VERSION" = "" ] ; then \
  apt-get -qqy update && \
  apt-get -qqy install git \
; fi

# Install Python3, pip, hapus OpenJDK 11, bersihkan cache
RUN apt-get -qqy update \
  && apt-get -qqy upgrade \
  && apt-get -qyy autoremove \
  && apt-get -qqy install python3 python-is-python3 pip \
  && apt-get -qyy remove openjdk-11-jre-headless \
  && apt-get -qyy autoremove \
  && apt-get -qyy clean \
  && rm -rf /var/lib/apt/lists/* /var/cache/apt/*

# Update entrypoint supervisor
COPY docker/supervisor.conf /etc/supervisor/conf.d/selenium.conf
COPY docker/supervisor-api.conf /etc/supervisor/conf.d/api.conf

# Ganti background image
COPY docker/background.png /usr/share/images/fluxbox/ubuntu-light.png

# Set direktori kerja
WORKDIR $G4F_DIR

# Copy dan install requirements (sebagai root)
COPY requirements.txt $G4F_DIR
RUN pip install --break-system-packages --upgrade pip \
  && pip install --break-system-packages -r requirements.txt

# Copy kode proyek
ADD --chown=$SEL_UID:$SEL_GID g4f $G4F_DIR/g4f

# Perbaiki permission folder lokal user
RUN chown -R "${SEL_UID}:${SEL_GID}" $HOME/.local $G4F_DIR

# Beralih ke user non-root
USER $SEL_UID

# Expose port
EXPOSE 8080 7900
