FROM python:3.6-alpine3.7
RUN apk add --no-cache py3-paramiko
ADD . /code
WORKDIR /code

RUN pip3 install -r requirements.txt

CMD ["python3", "pull.py"]
