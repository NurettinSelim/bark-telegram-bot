FROM --platform=linux/amd64 python:3.9-slim as build

WORKDIR /app
COPY . /app

RUN pip3 install -r requirements.txt

CMD ["python3", "main.py"]