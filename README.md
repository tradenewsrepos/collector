# trade_news_collector

## Aгрегатор новостных лент за текущие сутки

#### Основной код на базе репозитория <http://10.8.0.4:3050/shatilov-aa/coronavirus_texts_monitoring.git>

#### Модифицирован под задачи проекта "Торговые новости" Trade News

## Локальная установка

### Первоначальная установка для отладки под Ubuntu(WSL2) с помощью `venv` в `python`
  
```bash
git clone http://10.8.0.4:3050/chursin-sm/trade_news_collector.git
cd trade_news_collector
python3 -m venv venv
source ./venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## Создание контейнеров для работы

### Создать файл <b>.env</b>

### Указать в нем значения

 POSTGRES_USER=<b>user </b>

* POSTGRES_PASSWORD=<b>password</b>
* POSTGRES_HOST=<b>address</b>
* POSTGRES_PORT=<b>port</b>
* POSTGRES_DB=<b>news</b>

* DELTA_DATE_ARTICLE=<b>5</b> - просмотр новостей начиная с текущей даты минус DELTA_DATE_ARTICLE дней
* DELTA_DATE_TEXT=<b>5</b> - просмотр статей (новости подкобно) начиная с текущей даты минус DELTA_DATE_TEXT дней
* DOWNLOAD_ARTICLE_SLEEP=<b>60</b> - время ожидания процесса поиска новостей до следующего запуска в минутах
* DOWNLOAD_TEXT_SLEEP=<b>30</b> - время ожидания процесса чтения новостей до следующего запуска в минутах

### Последовательно войти в папки news_download и news_text_update
### Создать изапустить контейнеры: <b> docker compose up </b>

### Будут созданы и запущены на выполнение два контейнера  

* <b> news-collector-news-download </b> - парсинг и загрузка новостей с сайтов и новостных лент;
Запуск через каждый час после полного прохода по списку RSS и новостных сайтов.
* <b> news-collector-text-update </b> - обработка и запись в базу аннотаций новостей.
Запуск через каждые 30 мин после прохода по новостям в таблице article.
