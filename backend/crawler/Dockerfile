FROM alpine:latest
RUN apk update
RUN apk upgrade

#asyncssh-1.16.0 require cryptography-2.6.1, and need to build cryptography on Alpine
RUN apk add  --no-cache gcc musl-dev python3-dev libffi-dev openssl-dev py3-paramiko 

ADD . /code
WORKDIR /code
RUN pip3 install --upgrade pip
#RUN pip3 install 'asyncssh[bcrypt,gssapi,libnacl,pyOpenSSL]'
RUN pip3 install -r requirements.txt

CMD ["python3", "pull.py"]
