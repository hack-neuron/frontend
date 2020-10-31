# coding: utf-8

import os
import time

import aiohttp
import bcrypt
import jwt
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BACKEND_API_URL = os.environ['BACKEND_API_URL']
METADATA_API_URL = os.environ['METADATA_API_URL']

path = os.path.dirname(__file__)
static_path = os.path.join(path, 'static')
jwt_path = os.path.join(path, 'jwt.key')
jwt_path_pub = os.path.join(path, 'jwt.key.pub')

with open(jwt_path) as f:
    JWT_KEY = f.read()

with open(jwt_path_pub) as f:
    JWT_KEY_PUB = f.read()


app = FastAPI(
    title='Neuramark API',
    version='1.0.0',
    docs_url=None,
    redoc_url=None
)

app.mount('/static', StaticFiles(directory=static_path), name='static')


class Application(BaseModel):
    name: str
    password: str
    admin_email: str


class Credentials(BaseModel):
    name: str
    password: str


def create_token(name: str) -> str:
    return jwt.encode({'name': name, 'time': int(time.time())}, JWT_KEY, algorithm='RS256').decode()


async def check_token(token: str):
    try:
        payload = jwt.decode(token, JWT_KEY_PUB, algorithm='RS256')
    except jwt.exceptions.InvalidTokenError:  # type: ignore
        raise HTTPException(status_code=403, detail='Token error!')

    name = payload['name']

    async with aiohttp.ClientSession() as session:
        params = {'name': name}
        async with session.get(METADATA_API_URL + '/get_application', params=params) as resp:
            application = await resp.json()
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail=application.get('detail'))
            elif application['token'] != token:
                raise HTTPException(status_code=403, detail='Token expired!')


async def check_credentials(credentials: Credentials):
    async with aiohttp.ClientSession() as session:
        params = {'name': credentials.name}
        async with session.get(METADATA_API_URL + '/get_application', params=params) as resp:
            application = await resp.json()
            if resp.status != 200:
                raise HTTPException(status_code=403, detail='Permission denied!')
            else:
                hashed_password = application['password']
                if not bcrypt.checkpw(credentials.password.encode(), hashed_password.encode()):
                    raise HTTPException(status_code=403, detail='Permission denied!')
    return credentials


@app.post('/create_application')
async def create_application(application: Application):
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(application.password.encode(), salt)
    async with aiohttp.ClientSession() as session:
        token = create_token(application.name)
        data = {
            'name': application.name,
            'hashed_password': hashed_password.decode(),
            'admin_email': application.admin_email,
            'token': token
        }
        async with session.post(METADATA_API_URL + '/create_application', json=data) as resp:
            if resp.status == 200:
                return {'token': token}
            return await resp.json()


@app.delete('/delete_application')
async def delete_application(credentials: Credentials = Depends(check_credentials)):
    async with aiohttp.ClientSession() as session:
        params = {'name': credentials.name}
        async with session.delete(METADATA_API_URL + '/delete_application', params=params) as resp:
            application = await resp.json()
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail=application.get('detail'))
            return await resp.json()


@app.post('/revoke_token')
async def revoke_token(credentials: Credentials = Depends(check_credentials)):
    async with aiohttp.ClientSession() as session:
        token = create_token(credentials.name)
        data = {
            'name': credentials.name,
            'token': token
        }
        async with session.post(METADATA_API_URL + '/update_token', json=data) as resp:
            application = await resp.json()
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail=application.get('detail'))
            return {'token': token}


@app.get('/ping')
async def ping(token: str = Depends(check_token)):
    return {'ping': 'pong'}


@app.post('/upload')
async def upload(token: str = Depends(check_token),
                 doc_markup: UploadFile = File(...),
                 ai_markup: UploadFile = File(...),
                 scan: UploadFile = File(...)):
    # Проверка MIME загружаемых данных
    for upload_file in (doc_markup, ai_markup, scan):
        if upload_file.content_type != 'image/png':
            raise HTTPException(status_code=400, detail='File must be .png!')

    form = aiohttp.FormData()

    for k, v in {'doc_markup': doc_markup, 'ai_markup': ai_markup, 'scan': scan}.items():
        form.add_field(k, v.file.read(),
                       content_type=v.content_type,
                       filename=v.filename)
    async with aiohttp.ClientSession() as client:
        async with client.post(BACKEND_API_URL + '/upload', data=form) as resp:
            return await resp.json()


@app.post('/upload_many')
async def upload(token: str = Depends(check_token),
                 archive_file: UploadFile = File(...)):
    if archive_file.content_type != 'application/zip':
        raise HTTPException(status_code=400, detail='File must be .zip!')

    form = aiohttp.FormData()

    form.add_field('archive_file', archive_file.file.read(),
                   content_type=archive_file.content_type,
                   filename=archive_file.filename)
    async with aiohttp.ClientSession() as client:
        async with client.post(BACKEND_API_URL + '/upload_many', data=form) as resp:
            return await resp.json()


@app.get('/get_status')
async def get_status(id_: str,
                     token: str = Depends(check_token)):
    params = {'id_': id_}
    async with aiohttp.ClientSession() as client:
        async with client.get(BACKEND_API_URL + '/get_status', params=params) as resp:
            return await resp.json()


@app.get('/docs', include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f'{app.title} - Swagger UI',
        swagger_js_url='/static/js/swagger-ui-bundle.js',
        swagger_css_url='/static/css/swagger-ui.css'
    )
