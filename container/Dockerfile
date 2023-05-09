FROM docker.io/openjdk:21-slim-bullseye

RUN apt update
RUN apt install python3-pip -y

WORKDIR /tmp
COPY ./requirements.txt .
RUN pip install -r /tmp/requirements.txt

RUN groupadd --gid 1000 optapy \
  && useradd --uid 1000 --gid optapy --shell /bin/bash --create-home optapy
USER optapy

WORKDIR /home/optapy

ENTRYPOINT ["python3"]