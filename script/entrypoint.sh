#!bin/sh

cd /app

if [ $USE_SOCK_FILE = "True" ]
then
    uvicorn main:app --uds hack2020-front.sock
else
    uvicorn main:app --host 0.0.0.0 --port 80
fi
