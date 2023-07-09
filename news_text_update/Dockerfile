FROM python:3.9-slim-buster
# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# install google-chrome 
# uncomment when using Selenium
# RUN wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
# RUN sudo dpkg -i google-chrome-stable_current_amd64.deb
# RUN apt install --fix-broken -y
# RUN dpkg -i google-chrome-stable_current_amd64.deb
# RUN rm -f google-chrome-stable_current_amd64.deb

# set work directory
WORKDIR /code

ENV PYTHONPATH "${PYTHONPATH}:/code"

ARG SECRET_KEY
ARG POSTGRES_USER
ARG POSTGRES_PASSWORD
ARG POSTGRES_HOST
ARG POSTGRES_PORT
ARG POSTGRES_DB

# Основные зависимости
RUN apt update && apt install -y gcc

COPY ./requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt \
    #
    # Cleanup unnecessary stuff
    && apt-get purge -y  \
    -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/* \
    /tmp/*
# copy project
COPY . .

CMD ["python", "-u", "main_get_text.py"]