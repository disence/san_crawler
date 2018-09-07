FROM alpine:3.8
RUN apk add --no-cache python3 py3-paramiko
ADD . /code
WORKDIR /code

RUN pip3 install -r requirements.txt

CMD ["python3", "pull.py"]
