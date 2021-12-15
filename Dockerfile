FROM python:3.9.9-bullseye

# Definition of a Device & Service
ENV POSITION=Runtime \
    SERVICE=check-multiple-camera-multiple-device-connection \
    AION_HOME=/var/lib/aion

# Setup Directoties
RUN mkdir -p /${AION_HOME}/$POSITION/$SERVICE

WORKDIR /${AION_HOME}/$POSITION/$SERVICE

RUN apt-get update && apt-get install -y \
    v4l-utils \
    libmariadb-dev \
    build-essential \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

ADD . .

RUN pip3 install -r requirements.txt

RUN python3 setup.py install

CMD ["python3", "-m", "chkcamera"]
