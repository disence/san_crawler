FROM alpine:3.8
RUN apk add --no-cache python3
ADD . /code
WORKDIR /code
EXPOSE 8888
RUN pip3 install -r requirements.txt
CMD ["python3", "interface.py"]
