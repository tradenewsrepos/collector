import datetime
import html
import json
import random
import re
import time
import string

import feedparser
import requests
from bs4 import BeautifulSoup

from fake_useragent import UserAgent
from newspaper import Article as Article_news
from newspaper import ArticleException
# Перенести в отдельный модуль
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.common.keys import Keys
# from selenium.common.exceptions import NoSuchElementException
# Конец переноса

from transliterate import translit

from config import DELTA_DATE_TEXT, TFIDF_SERVER, engine
from models import Article, Feed
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker

# re_url = r"(?<Protocol>\w+):\/\/(?<Domain>[\w@][\w.:@]+)\/?[\w\.?=%&=\-@/$,]*"

def preprocess_text(text):
    exclude = set(string.punctuation)
    clean_text = "".join(i for i in text.strip() if i not in exclude)
    clean_text = re.sub(r'\n+', ' ', clean_text)
    # remove punctuation
    clean_text = re.sub(r'[^\w\s]', ' ', clean_text)
    
    # change multispaces to single space
    clean_text = re.sub(r'\s+', ' ', clean_text)
    
    # delete collocations with years
    pattern = r"\b(?:(\d{2}|\d{4})\s*(?:год(?:а|у)?|year))\b"
    clean_text = re.sub(pattern, "", clean_text)
    
    # delete collocations with separate years
    pattern = r"\b(?:(\d{2}|\d{4}))\b"
    clean_text = re.sub(pattern, "", clean_text)
    
    # delete months
    pattern = r'''January|February|March|April|May|June|July|August|September|October|November|December|январ[ья]|феврал[ья]|март[а]?|апрел[ья]|мая?|июн[ья]?(?:[яю]|е[ао])?|июл[ья]?[яи]?|август[а]?|сентябр[ья]?|октябр[ья]?|ноябр[ья]?|декабр[ья]'''
    clean_text = re.sub(pattern, "", clean_text, flags = re.I)
    
    return clean_text    


class CommonParser:
    """
    For exportcenter.ru etc.
    """

    def __init__(self, timeout=30, verify=True, headers=None):
        ua = UserAgent()
        self.timeout = timeout
        self.verify = verify
        self.headers = {"User-Agent": ua.random}
        if headers:
            self.headers.update(headers)

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url, timeout=self.timeout,
                        verify=self.verify, headers=self.headers)
        return r.status_code, r.url, r.text

    def parse(self, feed_url):
        rss_status, rss_url, rss_html = self.get(feed_url)
        result = feedparser.parse(rss_html)
        result["href"] = rss_url
        result["status"] = rss_status
        return result


def scrape_minpromtorg(article_news, url):
    news = CommonParser(verify=True).parse(
        "https://minpromtorg.gov.ru/api/ssp-news/v1/rss")
    for item in news["entries"]:
        if item["link"] == url:
            main_div = item["summary"]
            break
    article_news.download(input_html="<html>" + main_div + "</html>")


def scrape_eu_commission(article_news, url):
    doc_id = url.rsplit("/", 1)[1]
    doc_id = doc_id.replace("_", "/")
    url_json = f"https://ec.europa.eu/commission/presscorner/api/documents?reference={doc_id}&language=en"
    time.sleep(10)
    r = requests.get(url_json, timeout=30)
    res = r.json().get("docuLanguageResource")
    if res:
        article_news.download(input_html=res["htmlContent"])
    else:
        article_news.download(input_html="<html></html>")

def scrape_euraz_econ(article_news, url):
    # r = requests.get(url)
    # r_html = r.content.decode("utf-8")
    # soup = BeautifulSoup(r_html, features="html.parser")
    # main_div = soup.find("div", attrs={"div": "news-detail__body"})
    # article_news.download(input_html="<html>" + main_div.text + "</html>")
    soup = get_soup(url)
    main_div = soup.find("div", attrs={"div": "news-detail__body"})
    if main_div:
        article_news.download(input_html="<html>" + main_div.text + "</html>")

def scrape_mofa_japan(article_news, url):
    r = requests.get(url)
    r_html = r.content.decode("utf-8")
    soup = BeautifulSoup(r_html, features="html.parser")
    main_div = soup.find("div", attrs={"id": "maincontents"})
    article_news.download(
        input_html="<html>" + main_div.text.rsplit("Related Links", 1)[0] + "</html>")


def scrape_torg_pred(article_news, url):
    ua = UserAgent()
    country_code = re.findall(r"https\:\/\/(\w+)\.", url)[0]
    url_json = "https://{country_code}.minpromtorg.gov.ru/api/ssp-news/v1/?isCurrentSiteOnly=true&per_page=10&page=1".format(
        country_code=country_code)
    # # #  -------
    # sess_recv = requests.Session()
    # retry = Retry(connect=3, backoff_factor=0.5)
    # adapter = HTTPAdapter(max_retries=retry)
    # sess_recv.mount('https://', adapter)
    # # #   --------

    try:
        # r = sess_recv.get(url_json)
        r = requests.get(url_json, headers={
                        "User-Agent": ua.random}, verify=False)
        r_json = r.json()
        r_data = r_json.get("data")
        id_ = url.split("?id=")[-1]
        main_div = ""

        for item in r_data:
            if id_ == item.get("id"):
                main_div = item.get("text")
                break
        article_news.download(input_html="<html>" + main_div + "</html>")
    except Exception as e:
        print(e)

def get_soup(url: str):
    ua = UserAgent()
    r = requests.get(url, headers={"User-Agent": ua.random})
    try:
        r_html = r.content.decode("utf-8")
    except Exception as e:  
        print(f'Декодирован cp1251 {e}')   
        r_html = r.content.decode("cp1251")
    soup = BeautifulSoup(r_html, features="html.parser")
    return soup

def get_soup_not_verify(url: str):
    ua = UserAgent()
    r = requests.get(url, headers={"User-Agent": ua.random}, verify=False)
    try:
        r_html = r.content.decode("utf-8")
    except Exception as e:  
        print(f'Декодирован cp1251 {e}')   
        r_html = r.content.decode("cp1251")
    soup = BeautifulSoup(r_html, features="html.parser")
    return soup

def scrape_scmp(article_news, url):
    soup = get_soup(url)
    article_text = ""
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        s_json = json.loads(s.text)
        if "articleBody" in s_json:
            article_text = s_json["articleBody"]
            break
    article_news.download(input_html="<html>" + article_text + "</html>")


def scrape_anadolu(article_news, url):
    soup = get_soup(url)
    main_div = soup.find("div", attrs={"class": "detay-icerik"})
    article_news.download(input_html="<html>" + main_div.text + "</html>")


def scrape_mid(article_news, url):
    soup = get_soup(url)
    main_div = soup.find("div", attrs={"class": "page-inner"})
    article_news.download(input_html="<html>" + main_div.text + "</html>")


def scrape_cgtn(article_news, url):
    soup = get_soup(url)
    main_div = soup.find("div", attrs={"id": "cmsMainContent"})
    text_list = []
    if main_div:
        data_json = main_div.get("data-json")
        if data_json:
            data_json = json.loads(data_json)
            for d in data_json:
                content = d.get("content")
                if content:
                    text_list.append(content)
    text = " ".join(text_list)
    article_news.download(input_html="<html>" + text + "</html>")


def scrape_ngv(article_news, url):
    soup = get_soup(url)
    main_div = soup.find("div", attrs={"class": "project__wraper"})
    article_news.download(input_html="<html>" + main_div.text + "</html>")


def scrape_metalbulletin(article_news, url):
    soup = get_soup(url)
    main_div = soup.find("div", attrs={"class": "text1"})
    article_news.download(input_html="<html>" + main_div.text + "</html>")


def scrape_cdu(article_news, url):
    soup = get_soup(url)
    main_div = soup.find("div", attrs={"class": "article"})
    article_news.download(input_html="<html>" + main_div.text + "</html>")


def scrape_argus(article_news, url):
    ua = UserAgent()
    url = url.replace("/ru/", "/api/")
    url = re.sub(r"(\d{7})\-", r"\1/", url)
    r = requests.get(url, headers={"User-Agent": ua.random}, timeout=10)
    r_json = r.json()
    main_div = r_json.get("Body")
    article_news.download(input_html="<html>" + main_div + "</html>")


def scrape_businesslive(article_news, url):
    soup = get_soup(url)
    main_divs = soup.find_all("div", attrs={"class": "text"})
    if main_divs:
        main_text = " ".join([i.text for i in main_divs])
        main_text = main_text.replace("\xa0", " ")
    else:
        main_divs = soup.find_all("div", attrs={"class": "article-content"})
        main_text = str(main_divs)
    article_news.download(input_html="<html>" + main_text + "</html>")


def scrape_nyt(article_news, url):
    soup = get_soup(url)
    main_divs = soup.find_all("p", attrs={"class": re.compile(r"css.+")})
    main_divs = " ".join([str(i) for i in main_divs])
    article_news.download(input_html="<html>" + main_divs + "</html>")


# def scrape_selenium(article_news, url):
#     executable_path = "/mnt/appdata/containership_home/coronavirus_texts_monitoring/chromedriver"
#     timeout = 10
#     ua = UserAgent()
#     options = Options()
#     options.add_argument("--headless")
#     options.add_argument(f"user-agent={ua.random}")
#     driver = webdriver.Chrome(options=options, executable_path=executable_path)
#     driver.set_page_load_timeout(timeout)
#     try:
#         driver.get(url)
#     except TimeoutException:
#         driver.execute_script("window.stop();")
#     page_html = driver.page_source
#     if page_html:
#         page_html = html.unescape(page_html)
#         status_code = 200
#     else:
#         status_code = -1
#     driver.close()
#     article_news.download(input_html=page_html)


def scrape_africabusinesscommunities(article_news, url):
    soup = get_soup(url)
    main_div = soup.find_all("div", attrs={"class": "main-content"})
    if main_div:
        html = str(main_div[0])
    else:
        html = ""
    article_news.download(input_html="<html>" + html + "</html>")


def scrape_vz(article_news, url):
    soup = get_soup(url)
    main_div = soup.find_all("div", attrs={"class": "rel"})[0]
    main_div = str(main_div)
    article_news.download(input_html="<html>" + main_div + "</html>")


def scrape_vedomosti(article_news, url):
    soup = get_soup(url)
    main_div = soup.find_all("div", attrs={"class": "article__body"})[0]
    main_text = main_div.find_all("p", attrs={"class": "box-paragraph__text"})
    main_text = [str(d)
                for d in main_text if not d.text.startswith("Подписывайтесь")]
    main_text = "\n".join([t for t in main_text])
    article_news.download(input_html="<html>" + main_text + "</html>")


def scrape_exportcenter(article_news, url):
    soup = get_soup(url)
    main_div = soup.find("div", attrs={"class": "article__body"})
    article_news.download(input_html="<html>" + main_div.text + "</html>")


def scrape_common(article_news, url):
    ua = UserAgent()
    r = requests.get(url, headers={"User-Agent": ua.random}, timeout=10)
    if r.status_code != 200:
        raise ArticleException(r.status_code)
    r_html = r.content.decode("utf-8")
    article_news.download(r_html)

# Перенести в отдельный модуль
# def init_Selenium():
#     options = Options()
#     options.add_argument('--no-sandbox')
#     # options.add_argument('--disable-gpu')
#     # options.add_argument('--disable-dev-shm-usage')
#     # options.add_argument("--disable-extensions")
#     options.add_argument("--disable-notifications")
#     # options.add_argument('--headless')
#     # options.add_argument("--no-startup-window")
#     # options.add_argument('--start-minimized')

#     global service
#     service = Service(executable_path="./chromedriver")

#     global driver
#     driver = webdriver.Chrome(service=service, options=options)


# def get_parag(class_name_article: str, class_name_absaz):
#     elem = driver.find_element(By.CLASS_NAME, class_name_article)
#     time.sleep(3)
#     result_text = ''
#     elems_p = elem.find_elements(By.TAG_NAME, class_name_absaz)
#     for i in range(len(elems_p)):
#         result_text = result_text + "<p>" + elems_p[i].get_attribute("innerHTML") + "</p"
#     return result_text    
    
# def  scrape_bloomberg(article_news, url):
#     init_Selenium()
#     driver.get(url)
#     time.sleep(25)
#     # driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.END)
#     try:
#         result_text = get_parag('body-content', 'p')
#     except NoSuchElementException as e:
#         try:
#             result_text = get_parag('article-text', 'p')
#         except NoSuchElementException as e_a:
#             try:
#                 result_text = get_parag('grid-body', 'p')
#             except NoSuchElementException as e_a:
#                 try:
#                     elem = driver.find_element(By.CLASS_NAME, 'video-metadata__summary')
#                     result_text = elem.text
#                 except NoSuchElementException as e_a:
#                     print(f'Неправильно задан тег {e_a}')

#     body_content = "<html><div>" + result_text + "</div></html>"
#     article_news = Article_news(body_content)
#     article_news.download(input_html=body_content)
#     article_news.download_state = 200
#     url = driver.current_url
#     driver.close()
#     return (article_news, url)
# Конец перенести в отдельный модуль


ParserByName = {
    "africabusinesscommunities": scrape_africabusinesscommunities,
    "anadolu": scrape_anadolu,
    "argus": scrape_argus,
    "businesslive": scrape_businesslive,
    # "bloomberg": scrape_bloomberg,
    "cdu": scrape_cdu,
    "cgtn_eurasian": scrape_cgtn,
    "izvestia": scrape_common,
    "eu_commission": scrape_eu_commission,
    "exportcenter": scrape_exportcenter,
    "metalbulletin": scrape_metalbulletin,
    "mid": scrape_mid,
    "minpromtorg": scrape_minpromtorg,
    "mofa_japan": scrape_mofa_japan,
    "ngv": scrape_ngv,
    "nyt": scrape_nyt,
    "scmp": scrape_scmp,
    # "dailynewsegypt": scrape_selenium,
    "vedomosti": scrape_vedomosti,
    "vz.ru": scrape_vz,
    "torg_pred_": scrape_torg_pred,
    # "euraz.econ.com": scrape_euraz_econ,
}


class FeedTextDownloader():
    """
    Main class for feed downloads and database updates.
    Used in cron jobs for periodical updates.
    """

    def __init__(self):
        self.rss_raw = {}

        Session = sessionmaker(engine)
        self.session = Session()
        # url_remove = re.compile(re_url)

    def get_datetime(self, delta):
        return (datetime.datetime.now(
            datetime.timezone.utc) + datetime.timedelta(delta)).replace(hour=0, minute=0, second=0, microsecond=0)

    def get_texts(self):
        """
        Scrape and parse news texts
        """
        time.sleep(5)

        start_date = self.get_datetime(-DELTA_DATE_TEXT)
        end_date = self.get_datetime(1)

        articles_to_parse = self.session.execute(select(Article.id, Article.url, Article.feed_id,
                                                        Article.published_parsed, Article.title,
                                                        Feed.url, Feed.tags, Feed.name).where(
            Article.is_text_parsed == False,
            Feed.used == True,
            Feed.available == True,
            Article.published_parsed >= start_date,
            Article.published_parsed <= end_date, 
            Feed.id == Article.feed_id)
            .order_by(Article.published_parsed.desc())).all()

        random.shuffle(articles_to_parse)
        count = 0
        for article in articles_to_parse:
            try:
                if article.tags.find("ru") > 0:
                    lang = "ru"
                else:
                    lang = "en"
                print(
                    f'Id = {article.feed_id} ->  {article.published_parsed.date()} сайт {article.url} статья - "{article.title}"')

                article_news = Article_news(article.url, language=lang)

                if article.name in ParserByName:
                    ParserByName[article.name](article_news, article.url)
                elif "torg_pred_" in article.name:
                    scrape_torg_pred(article_news, article.url)
                elif "cgtn_" in article.name:
                    scrape_cgtn(article_news, article.url)
                # elif "bloomberg" in article.name:
                #     rez = scrape_bloomberg(article_news, article.url)
                #     article_news = rez[0]
                #     url = rez[1]    
                else:
                    article_news.download()

                article_news.parse()    

                text = re.sub("\n{2,}", " ", article_news.text)
                if any(
                    text.startswith(i)
                    for i in ["Регистрация пройдена успешно!", "Please Enable Cookies", "Access Denied", "Your username or password is invalid"]
                ):
                    print("Will retry next time")
                    continue
                if text == '':
                    continue
                else:
                    # if article.feed_id == 2027:
                    #     self.session.execute(update(Article).where(Article.id == article.id).values(
                    #     text=text, is_text_parsed=True, url=url))
                    # else:  
                    prom_text = article.title+'/n/n'+text 
                    clean_text = preprocess_text(prom_text)
                    probability = requests.post(TFIDF_SERVER, json={"text": clean_text}).json() 
                    self.session.execute(update(Article).where(Article.id == article.id).values(
                    text = text, is_text_parsed = True, sentiment = probability["score 2"]))
                    count += 1
                    self.session.commit()
                time.sleep(0.3)
            except Exception as e:
                print(e)
        print(f'Обработано {count} записей')
        self.session.close()
