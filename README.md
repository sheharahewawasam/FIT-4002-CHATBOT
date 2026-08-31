# FIT-4002-CHATBOT

## How to run it locally

1. Make sure you have all the requirements installed
2. Open index
3. cd into mvp_demo
4. run python manage.py runserver
5. pull both models in ollama (or whatever models you are testing with)
6. Boom bang everything should work

## Common Issues

1. no env file, keys should be in the shared folder in the api keys folder
2. Make sure your env file is named secrets.env or you can change the call to the name in ingest.py and views.py, up2u

## Ollama guide

1. Install Ollama
2. Pull whatever the models used in views.py into ollama

## PaddleOCR Guide

1. Install PaddlePaddle framework

```
python -m pip install paddlepaddle==3.3.0 -i https://www.paddlepaddle.org.cn/packages/stable/cpu/
```

2. Install PaddleOCR

```
python -m pip install paddleocr[all]
```

## Pinecone Guide

1. Install Pinecone

```
pip install pinecone
```

2. Install BM25

```
pip install pinecone-text
```


# Run Grader.py
0. Run the thing first/ make sure its working (ollama is pulled etc)
1. cd into mvp_demo
2. python -u ragmetrics\Grader.py *> log.txt
3. look it log.txt as the results populate