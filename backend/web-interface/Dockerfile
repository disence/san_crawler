FROM alpine:3.5
RUN apk add --no-cache python3 py3-paramiko
ADD . /code
WORKDIR /code
EXPOSE 8888
RUN pip3 install -r requirements.txt
CMD ["python3", "interface.py"]
