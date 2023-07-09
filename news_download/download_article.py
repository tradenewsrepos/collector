import datetime
import time
import html
import json
import re
import urllib.parse
from time import mktime, struct_time
from datetime import timezone

import warnings
import feedparser
import pytz
import requests
from bs4 import BeautifulSoup

from fake_useragent import UserAgent

# from selenium import webdriver
# from selenium.common.exceptions import TimeoutException
# from selenium.webdriver.chrome.options import Options
from transliterate import translit
from config import DELTA_DATE_ARTICLE, is_leap_year, engine
from models import Article, Feed, ExcludedFilter
from sqlalchemy import select, update
from sqlalchemy.orm import sessionmaker, Session
from filter.preprocessing import check_stop_words

MSK = pytz.timezone("Europe/Moscow")
ru_month_dict = {
    "январ": "01",
    "феврал": "02",
    "март": "03",
    "апрел": "04",
    "май": "05",
    "мая": "05",
    "июн": "06",
    "июл": "07",
    "август": "08",
    "сентябр": "09",
    "октябр": "10",
    "ноябр": "11",
    "декабр": "12",
}

Monats = {
    "января": "01",
    "февраля": "02",
    "марта": "03",
    "апреля": "04",
    "мая": "05",
    "июня": "06",
    "июля": "07",
    "августа": "08",
    "сентября": "09",
    "октября": "10",
    "ноября": "11",
    "декабря": "12",
}

month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


class BaseParser:
    """ """

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, headers={"User-Agent": ua.random}, timeout=30, verify=False
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, features="html.parser")
        return soup

    def clear_space_hyp(self, value):
        value = value.strip(" ")
        value = value.strip("\n")
        value = value.strip(" ")
        return value


class MontsameParser:
    """
    Class to parse https://montsame.mn/ru/highlights?class=list news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://montsame.mn/ru/"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url, verify=False)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "montsame",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        d_now = datetime.datetime.now(tz=pytz.timezone("Europe/Moscow"))

        for item in soup.find_all("div", {"class": "news-box-list mr-3"}):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            url_relative = item.find("a").get("href")
            id_ = url_relative.replace("/", "_")
            feed_item["id"] = id_

            feed_item["title"] = item.find("div", {"class": "title"}).text
            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, url_relative)

            time_data = item.find("div", {"class": "stat d-block"}).text
            val, measure = re.findall(r"(\d+) (\w+)", time_data)[0]
            measure = measure.lower()
            val = int(val)

            delta_days = 0
            delta_seconds = 0

            if measure.startswith("д"):
                delta_days = val
            elif measure.startswith("ч"):
                delta_seconds = 60 * 60 * val
            elif measure.startswith("м"):
                delta_seconds = 60 * val
            elif measure.startswith("с"):
                delta_seconds = val

            d_item = d_now - \
                datetime.timedelta(days=delta_days, seconds=delta_seconds)
            d_item = (
                d_item.replace(hour=0)
                .replace(minute=0)
                .replace(second=0)
                .replace(microsecond=0)
            )
            feed_item["published_parsed"] = struct_time(d_item.timetuple())

            result["entries"].append(feed_item)
        return result


class TorgPredParser:
    """
    Class to parse "https://<country_code>.minpromtorg.gov.ru/news/" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://{country_code}.minpromtorg.gov.ru"
        self.url_json = "https://{country_code}.minpromtorg.gov.ru/api/ssp-news/v1/?isCurrentSiteOnly=true&per_page=20&page=1"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(url, headers={"User-Agent": ua.random}, verify=False)
        if r.status_code != 200:
            return None
        r_json = r.json()
        return r_json

    def parse(self, feed_url):
        country_code = re.findall(r"https\:\/\/(\w+)\.", feed_url)[0]
        self.url_base = self.url_base.format(country_code=country_code)
        self.url_json = self.url_json.format(country_code=country_code)
        result = {
            "feed": {
                "title": f"torg_pred_{country_code}",
            },
            "href": feed_url,
            "entries": [],
        }

        r_json = self.get(self.url_json)
        if not r_json:
            return result

        r_data = r_json.get("data")
        if not r_data:
            return result

        for item in r_data:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            url_friendly = item.get("friendlyUrl")
            id_ = item.get("id")
            url_relative = f"/news?id={id_}"
            feed_item["id"] = id_

            feed_item["title"] = item.get("title").strip()
            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, url_relative)

            time_data = item.get("date")
            if time_data:
                time_data = time_data[:10]
                feed_item["published_parsed"] = struct_time(
                    datetime.datetime.strptime(
                        time_data, "%Y-%m-%d").timetuple()
                )

            if feed_item["published_parsed"] >= struct_time(
                datetime.datetime.strptime(
                    "2022-12-25", "%Y-%m-%d").timetuple()
            ):
                result["entries"].append(feed_item)
        return result


class ReutersParser:
    """
    Class to parse "https://www.reuters.com" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.reuters.com"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "reuters",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        data1, data2 = (
            str(soup.html)
            .split("globalContent=", 1)[1]
            .split(";Fusion.globalContentConfig=")
        )
        data2 = data2.split(";Fusion.contentCache=")[
            1].split(";Fusion.layout")[0]
        data1 = json.loads(data1)
        data2 = json.loads(data2)

        data1_articles = data1["result"]["articles"]
        for item in data1_articles:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            feed_item["id"] = item["id"]
            feed_item["title"] = item["title"]
            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, item["canonical_url"]
            )
            feed_item["published_parsed"] = datetime.datetime.strptime(
                item["published_time"][:16], "%Y-%m-%dT%H:%M"
            ).timetuple()
            if feed_item not in result["entries"]:
                result["entries"].append(feed_item)

        for article_group in [
            "articles-by-collection-alias-or-id-v1",
            "articles-by-section-alias-or-id-v1",
        ]:
            for k in data2[article_group]:
                group_articles = data2[article_group][k]
                try:
                    group_articles = group_articles["data"]["result"]["articles"]
                except KeyError:
                    continue
                for item in group_articles:
                    feed_item = {
                        "title": None,
                        "published_parsed": None,
                        "link": None,
                        "id": None,
                    }
                    feed_item["id"] = item["id"]
                    feed_item["title"] = item["title"]
                    feed_item["link"] = urllib.parse.urljoin(
                        self.url_base, item["canonical_url"]
                    )
                    feed_item["published_parsed"] = datetime.datetime.strptime(
                        item["published_time"][:16], "%Y-%m-%dT%H:%M"
                    ).timetuple()
                    if feed_item not in result["entries"]:
                        result["entries"].append(feed_item)

        return result


class XinhuaParser:
    """
    Class to parse news from "https://english.news.cn/indepth/index.htm" - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://english.news.cn"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, features="html.parser")
        return soup

    def parse(self, feed_url: str):
        result = {
            "feed": {
                "title": "xinhua",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            print("soup is none")
            return result

        for item in soup.find_all("div", {"class": "tit"}):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            url_relative = item.find("a").get("href")
            id_ = url_relative.replace("/", "_")
            feed_item["id"] = id_

            feed_item["title"] = item.find("a").text
            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, url_relative)

            time_data = item.find("span", {"class": "time"}).text
            feed_item["published_parsed"] = time.strptime(
                time_data, "%Y-%m-%d %H:%M:%S"
            )
            result["entries"].append(feed_item)
        return result


class USDepartmentOfTreasuryParser:
    """
    Class to parse "https://home.treasury.gov/news/press-releases" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://home.treasury.gov"
        self.url_feed = "https://home.treasury.gov/news/press-releases"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "us_department_of_treasury",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        news_div = soup.find("div", attrs={"class": "content--2col__body"})
        items = news_div.find_all("div")

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            headline = item.find("h3")
            if headline:
                headline = headline.find("a")
                title_i = headline.text
                href = headline.get("href")
                url_i = urllib.parse.urljoin(self.url_base, href)
            else:
                continue
            date_i = item.find("time")
            date_i = date_i.get("datetime")
            date_i = datetime.datetime.strptime(
                date_i, "%Y-%m-%dT%H:%M:%SZ"
            ).timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class APNewsParser:
    """
    Class to parse "https://apnews.com/hub/ap-top-news" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://apnews.com"
        self.url_feed = "https://apnews.com/hub/ap-top-news"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "apnews",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "FeedCard"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            title_i = item.find("h2", attrs={"class": "-cardHeading"}).text
            href = item.find("a", attrs={"data-key": "card-headline"})
            if not href:
                href = item.find(
                    "a", attrs={"class": re.compile(r"Component-link.+")})
            href = href.get("href")
            url_i = urllib.parse.urljoin(self.url_base, href)
            date_i = item.find(
                "span", attrs={"data-key": "timestamp"})["data-source"]
            date_i = datetime.datetime.strptime(
                date_i, "%Y-%m-%dT%H:%M:%SZ"
            ).timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class AgroobzorParser:
    """
    Class to parse "https://agroobzor.ru/news.html" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://agroobzor.ru"
        self.url_feed = "https://agroobzor.ru/news.html"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "agroobzor",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "blog-content"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            a = item.find("a")
            title_i = a.text.strip()
            href = a.get("href")
            url_i = urllib.parse.urljoin(self.url_base, href)

            date_i = item.find("time")["datetime"]
            date_i = datetime.datetime.strptime(
                date_i, "%Y-%m-%dT%H:%M:%S+03:00"
            ).timetuple()  # 2022-04-12T05:16:37+03:00

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class MOFAJapanParser:
    """
    Class to parse "https://www.mofa.go.jp/press/release/index.html" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.mofa.go.jp"
        self.url_feed = "https://www.mofa.go.jp/press/release/index.html"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "mofa_japan",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        dts = soup.find_all("dt", attrs={"class": "list-title"})
        date_now = datetime.datetime.now()

        for dt in dts:
            date_i = datetime.datetime.strptime(
                dt.text, "%B %d"
            )  # .timetuple()  # April 14
            if date_i.month == 12 and date_now.month == 1:
                # если в январе парсим декабрь
                date_i = date_i.replace(year=date_now.year - 1)
            else:
                date_i = date_i.replace(year=date_now.year)

            date_i = date_i.timetuple()

            dd_i = dt.find_next("dd")
            as_i = dd_i.find_all("a")

            for a in as_i:
                feed_item = {
                    "title": None,
                    "published_parsed": None,
                    "link": None,
                    "id": None,
                }

                title_i = a.text
                href = a["href"]
                url_i = urllib.parse.urljoin(self.url_base, href)

                feed_item["id"] = href
                feed_item["title"] = title_i
                feed_item["link"] = url_i
                feed_item["published_parsed"] = date_i
                result["entries"].append(feed_item)

        return result


class CommonParser:
    """
    For exportcenter.ru etc.
    """

    def __init__(self, timeout=60, verify=True, headers=None):
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
        r = requests.get(
            url, timeout=self.timeout, verify=self.verify, headers=self.headers
        )
        return r.status_code, r.url, r.text

    def parse(self, feed_url):
        rss_status, rss_url, rss_html = self.get(feed_url)
        result = feedparser.parse(rss_html)
        result["href"] = rss_url
        result["status"] = rss_status
        return result


class MIDParser:
    """
    For mid.ru
    """

    def __init__(self):
        pass

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(url, timeout=30, headers={"User-Agent": ua.random})
        if r.status_code != 200:
            return None
        return r.text

    def parse(self, feed_url):
        rss_html = self.get(feed_url)
        result = feedparser.parse(rss_html)
        return result


class JapanNewsParser:
    """
    Class to parse "https://japannews.yomiuri.co.jp" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://japannews.yomiuri.co.jp"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, features="html.parser")
        return soup

    def parse(self, feed_url):
        category = feed_url.strip("/").rsplit("/", 1)[1]
        result = {
            "feed": {
                "title": f"japan_news_{category}",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("li", attrs={"class": "clearfix"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            title_i = item.find("h2").text
            href = item.find("a").get("href")
            url_i = href
            date_i = item.find("p").text
            date_i = date_i.split(" - ")[0].strip()
            date_i = datetime.datetime.strptime(
                date_i, "%B %d, %Y").timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class IQNAParser:
    """
    Class to parse "https://www.iqna.ir/ru/allnews" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.iqna.ir"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "iqna",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "text_container"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            a = item.find("a")
            title_i = a.get("title")
            href = a.get("href")
            url_i = urllib.parse.urljoin(self.url_base, href)

            time_i = item.find(
                "div", attrs={"class": "date_akhv"}).text.strip()
            date_i = datetime.datetime.strptime(
                time_i, "%H:%M , %Y %b %d"
            ).timetuple()  # 10:37 , 2022 Apr 27

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class CRIParser:
    """
    Class to parse "http://russian.cri.cn/news/homeList/index.html" and "http://russian.cri.cn/news/interList/index.html" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "http://russian.cri.cn"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "cri",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find("div", attrs={"class": "news-list"}).find_all("a")

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            title_i = item.text
            url_i = item.get("href")

            if url_i:
                time_i = url_i.rsplit("/", 2)[-2]
                date_i = datetime.datetime.strptime(
                    time_i, "%Y%m%d"
                ).timetuple()  # 20220425

            feed_item["id"] = url_i
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class RuChinaParser:
    """
    Class to parse "http://russian.china.org.cn" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "http://russian.china.org.cn"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        r = requests.get(url)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        feed_title_parts = feed_url.split("/")
        feed_title = feed_title_parts[-2]
        if feed_title == "business":
            node_string = feed_title_parts[-1].split(".")[0]
            if node_string[-1] == "6":
                node_name = "inside"
            elif node_string[-1] == "7":
                node_name = "opinions"
            elif node_string[-1] == "8":
                node_name = "trade"
            feed_title = f"{feed_title}_{node_name}"
        result = {
            "feed": {
                "title": f"ru_china_{feed_title}",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("td", attrs={"class": re.compile(r"a12_[^F]+")})

        for item in items[1:]:  # без заголовка
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            a = item.find("a")
            if a:
                href = a.get("href")
                if href and ("txt" in href):
                    url_i = href
                    title_i = a.text.strip("\u200b")
                    date_i = item.text[:16]  # 2022-04-29 16:18
                    date_i = datetime.datetime.strptime(
                        date_i, "%Y-%m-%d %H:%M"
                    ).timetuple()

                    feed_item["id"] = url_i
                    feed_item["title"] = title_i
                    feed_item["link"] = url_i
                    feed_item["published_parsed"] = date_i
                    result["entries"].append(feed_item)
                else:
                    continue
            else:
                continue

        return result


class CGTNParser:
    """
    Class to parse "https://russian.cgtn.com" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://russian.cgtn.com"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        feed_title_parts = feed_url.split("/")
        feed_title = feed_title_parts[-1]

        result = {
            "feed": {
                "title": f"cgtn_{feed_title}",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "cg-content-description"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            a = item.find("a")
            if a:
                href = a.get("href")
                if href:
                    url_i = href
                    title_i = a.text.strip()
                    date_i = item.find("div", attrs={"class": "cg-time"})
                    if date_i:
                        date_i = date_i.text.strip().rsplit(" ", 1)[
                            0
                        ]  # 29 Apr, 2022 00:30 GMT+8
                        date_i = datetime.datetime.strptime(
                            date_i, "%d %b, %Y %H:%M"
                        ).timetuple()

                    feed_item["id"] = url_i
                    feed_item["title"] = title_i
                    feed_item["link"] = url_i
                    feed_item["published_parsed"] = date_i
                    result["entries"].append(feed_item)
                else:
                    continue
            else:
                continue

        return result


class NGVParser:
    """
    Class to parse "http://www.ngv.ru/news/" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "http://www.ngv.ru"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "ngv",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "big-news-card"}) + soup.find_all(
            "div", attrs={"class": "news-card"}
        )
        date_now = datetime.datetime.now()

        for item in items:
            if len(item.get("class")) > 1:
                continue
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            a = item.find("a")
            if a:
                href = a.get("href")
                if href:
                    url_i = urllib.parse.urljoin(self.url_base, href)

                title_i = a.text
                if title_i:
                    title_i = title_i.strip()

            date_string_i = item.find(
                "span", attrs={"class": re.compile(r"(big\-)?news-card__date")}
            )
            if date_string_i:
                date_string_i = date_string_i.text.strip()
                for m in ru_month_dict:
                    if m in date_string_i:
                        pattern = f"{m}\w?"
                        date_string_i = re.sub(
                            pattern, ru_month_dict[m], date_string_i)
                        break
                date_string_i = re.sub(r"\s{2,}", " ", date_string_i)

                date_i = datetime.datetime.strptime(
                    date_string_i, "%d %m %Y"
                )  # 11 05 2022
                date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class MetalBulletinParser:
    """
    Class to parse "https://www.metalbulletin.ru/news/" news - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.metalbulletin.ru"
        self.ru_month_dict = {
            "янв": "01",
            "фев": "02",
            "мар": "03",
            "апр": "04",
            "май": "05",
            "июн": "06",
            "июл": "07",
            "авг": "08",
            "сен": "09",
            "окт": "10",
            "ноя": "11",
            "дек": "12",
        }

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "metalbulletin",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        main_div = soup.find("div", attrs={"class": "one_news"})
        main_div = main_div.find("table")

        for tr in main_div.find_all("tr"):
            if tr.get("bgcolor"):
                date_main = re.sub(r"\s+", " ", tr.text).strip()
                day, month, year = re.findall(r"(\d{2})\s(\w+)\.\s(\d{4})", date_main)[
                    0
                ]
                month = month.lower()
                month = self.ru_month_dict.get(month)
                date_main = datetime.datetime.strptime(
                    f"{year}.{month}.{day}", "%Y.%m.%d"
                )
            else:
                feed_item = {
                    "title": None,
                    "published_parsed": None,
                    "link": None,
                    "id": None,
                }
                all_tds = tr.find_all("td")
                if len(all_tds) == 2:
                    time_i, title_href = all_tds
                    hour, minute = [int(i) for i in time_i.text.split(":")]
                    date_i = date_main.replace(hour=hour, minute=minute)
                    date_i = date_i.timetuple()
                    title_i = title_href.text
                    href_i = title_href.find("a")
                    if href_i:
                        href_i = href_i.get("href")
                        url_i = href_i
                        feed_item["id"] = href_i
                        feed_item["title"] = title_i
                        feed_item["link"] = url_i
                        feed_item["published_parsed"] = date_i
                        result["entries"].append(feed_item)
        return result


class CDUParser:
    """
    Class to parse "https://www.cdu.ru/tek_russia/articles" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.cdu.ru"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=False, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "cdu",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"id": re.compile(r"article.+")})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            a = item.find("a")
            if a:
                href = a.get("href")
                url_i = urllib.parse.urljoin(self.url_base, href)
                title_i = a.text

            date_string_i = item.find("footer")
            if date_string_i:
                date_string_i = date_string_i.text.lower()
                year = re.findall(r"20\d\d", date_string_i)[0]
                for m in ru_month_dict:
                    if re.findall(m, date_string_i):
                        month = ru_month_dict[m]
                        break
                if year and month:
                    date_i = datetime.datetime.strptime(
                        f"{year}.{month}.01", "%Y.%m.%d"
                    )

                date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class ArgusParser:
    """
    Class to parse "https://www.argusmedia.com/ru/news" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.argusmedia.com"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "argus",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all(
            "div", attrs={"class": "article-content-container"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            h1 = item.find("h1")
            if h1:
                title_i = h1.text.strip()

            href = h1.find("a")
            if href:
                href = href.get("href")
                url_i = urllib.parse.urljoin(self.url_base, href)

            date_string_i = item.find("div", attrs={"class": "article-date"})
            if date_string_i:
                date_string_i = date_string_i.text.strip()

                for m in ru_month_dict:
                    if m in date_string_i:
                        pattern = f"{m}\w?"
                        date_string_i = re.sub(
                            pattern, ru_month_dict[m], date_string_i)
                        break
                date_i = datetime.datetime.strptime(date_string_i, "%d %m %Y")
                date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class MilknewsParser:
    """
    Class to parse "https://milknews.ru/index/" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://milknews.ru"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "milknews",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "news-list__item"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            if item.find("h2", attrs={"class": "section__subtitle"}):
                continue

            title_i = item.find("div", attrs={"class": "card__text"})
            if title_i:
                title_i = title_i.text.strip()

            href = item.find("a", attrs={"class": "block-link"})
            if href:
                href = href.get("href")
                url_i = urllib.parse.urljoin(self.url_base, href)

            date_string_i = item.find("date", attrs={"class": "card__date"})
            if date_string_i:
                date_string_i = date_string_i.text.strip()
                date_string_i = date_string_i.lower().replace("г.", " ")
                for m in ru_month_dict:
                    if m in date_string_i:
                        pattern = f"{m}\w?"
                        date_string_i = re.sub(
                            pattern, ru_month_dict[m], date_string_i)
                        break
                date_string_i = re.sub(r"\s{2,}", " ", date_string_i)
                date_string_i

                date_i = datetime.datetime.strptime(
                    date_string_i, "%d %m %Y %H:%M"
                )  # 11 05 2022 10:00
                date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class APKInformParser:
    """
    Class to parse "https://www.apk-inform.com/en/news" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.apk-inform.com"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "apkinform",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "content-news-text"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            a = item.find("a", attrs={"class": "text"})
            if a:
                title_i = a.text.strip()

                href = a.get("href")
                if href:
                    url_i = urllib.parse.urljoin(self.url_base, href)

            date_string_i = item.find("time", attrs={"class": "date"})
            if date_string_i:
                date_string_i = date_string_i.get("datetime")
                if date_string_i:
                    date_i = datetime.datetime.strptime(
                        date_string_i, "%B %d, %Y %H:%M"
                    )
                    date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class AfricabusinesscommunitiesParser:
    """
    Class to parse "https://africabusinesscommunities.com/news/" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://africabusinesscommunities.com"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "africabusinesscommunities",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "newsitem"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            a = item.find("a")
            if a:
                title_i = a.text.strip()

                href = a.get("href")
                if href:
                    url_i = urllib.parse.urljoin(self.url_base, href)

            date_string_i = item.find("span", attrs={"class": "meta"})
            if date_string_i:
                date_string_i = date_string_i.text
                if date_string_i:
                    date_i = datetime.datetime.strptime(
                        date_string_i, "%m-%d-%Y | %H:%M:%S"
                    )  # 05-17-2022 | 11:03:00
                    date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class AfricanewsParser:
    """
    Class to parse "https://www.africanews.com/news/" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.africanews.com"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "africanews",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("article", attrs={"class": "just-in__article"})
        urls = []

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            a = item.find("a")
            if a:
                title_i = a.text.strip()

                href = a.get("href")
                if href:
                    url_i = urllib.parse.urljoin(self.url_base, href)

            timestamp_i = item.get("data-created")
            if timestamp_i:
                timestamp_i = int(timestamp_i)
                date_i = datetime.datetime.fromtimestamp(timestamp_i)
                date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i

            if url_i not in urls:
                urls.append(url_i)
                result["entries"].append(feed_item)

        return result


class NuzParser:
    """
    Class to parse "https://nuz.uz/feed" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://nuz.uz"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "nuz.uz",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "item-details"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            h = item.find("h3")
            a = h.find("a")
            if a:
                title_i = a.text.strip()
                href = a.get("href")
                if href:
                    url_i = href

            date_string_i = item.find("time", attrs={"class": "entry-date"})
            if date_string_i:
                date_string_i = date_string_i.get("datetime")
                if date_string_i:
                    date_string_i = date_string_i.split("+")[0]
                    date_i = datetime.datetime.strptime(
                        date_string_i, "%Y-%m-%dT%H:%M:%S"
                    )  # 2022-05-18T13:01:51+00:00
                    date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i

            result["entries"].append(feed_item)

        return result


class MofcomParser:
    """
    Class to parse "http://english.mofcom.gov.cn/article/newsrelease/significantnews/" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "http://english.mofcom.gov.cn"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "mofcom",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        news_lst = soup.find_all("ul", attrs={"class": "txtList_01"})
        if news_lst:
            news_lst = news_lst[0]
        else:
            return result

        items = news_lst.find_all("li")

        for item in items:
            if item.get("class"):
                continue

            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            a = item.find("a")
            if a:
                title_i = a.text.strip()

                href = a.get("href")
                if href:
                    url_i = urllib.parse.urljoin(self.url_base, href)

            date_string_i = item.find("script")
            if date_string_i:
                date_string_i = re.findall(
                    r"\d{4}\-\d{2}\-\d{2} \d{2}\:\d{2}\:\d{2}", date_string_i.text
                )
                if date_string_i:
                    date_i = datetime.datetime.strptime(
                        date_string_i[0], "%Y-%m-%d %H:%M:%S"
                    )
                    date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class CommerceGovInParser:
    """
    Class to parse "https://commerce.gov.in/press-releases/" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://commerce.gov.in"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "commerce_gov_in",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("div", attrs={"class": "whats-new-wrapper"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            a = item.find("a")
            if a:
                title_i = a.text.strip()

                href = a.get("href")
                if href:
                    url_i = href

            date_string_i = item.find(
                "div", attrs={"class": "whats-new-calander"})
            if date_string_i:
                date_string_i = re.findall(
                    r".+(\d+)\w+\s{1,}(\w+)\s{1,}(\d+)", date_string_i.text.strip()
                )
                if date_string_i:
                    date_i = datetime.datetime.strptime(
                        " ".join(date_string_i[0]).lower(), "%d %B %Y"
                    )
                    date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i
            result["entries"].append(feed_item)

        return result


class ThedticParser:
    """
    Class to parse "http://www.thedtic.gov.za/category/the-dti-archives/media-room/media-statements/" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "http://www.thedtic.gov.za"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "thedtic",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        news_table = soup.find_all("table", attrs={"id": "search_table"})
        if news_table:
            news_table = news_table[0]
        else:
            return result

        for tr in news_table.find_all("tr"):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            all_tds = tr.find_all("td")
            if len(all_tds) == 2:
                title_href, time_i = all_tds
                a = title_href.find("a")
                if a:
                    url_i = a.get("href")
                    href = url_i
                    title_i = a.text.strip()

                date_string_i = time_i.text
                if date_string_i:
                    date_i = datetime.datetime.strptime(
                        date_string_i, "%B %d, %Y")
                    date_i = date_i.timetuple()

                feed_item["id"] = href
                feed_item["title"] = title_i
                feed_item["link"] = url_i
                feed_item["published_parsed"] = date_i
                result["entries"].append(feed_item)

        return result


class ExportcenterParser:
    """
    Class to parse "https://www.exportcenter.ru/press_center/" news
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.exportcenter.ru"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.get(
            url, timeout=30, verify=True, headers={"User-Agent": ua.random}
        )
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup

    def parse(self, feed_url):
        result = {
            "feed": {
                "title": "exportcenter",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            return result

        items = soup.find_all("article", attrs={"class": "news-card"})

        for item in items:
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            h = item.find("h3", attrs={"class": "news-card__title"})
            if h:
                title_i = h.text.strip()
            a = item.find("a", attrs={"class": "card-tile__link"})
            if a:
                href = a.get("href")
                if href:
                    url_i = urllib.parse.urljoin(self.url_base, href)

            date_string_i = item.find("time", attrs={"class": "date__time"})
            if date_string_i:
                date_string_i = date_string_i.get("datetime")
                if date_string_i:
                    date_i = datetime.datetime.strptime(
                        date_string_i, "%Y-%m-%d %H:%M"
                    )  # 2022-05-18 13:01
                    date_i = date_i.timetuple()

            feed_item["id"] = href
            feed_item["title"] = title_i
            feed_item["link"] = url_i
            feed_item["published_parsed"] = date_i

            result["entries"].append(feed_item)

        return result


class MinEconDevelParser(BaseParser):
    """
    Class to parse news from "https://economy.gov.ru/material/news/" - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://economy.gov.ru/material/news/"

    def parse(self, feed_url: str):
        result = {
            "feed": {
                "title": "min.econom",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            print("soup is none")
            return result

        for item in soup.find_all("div", {"class": "e-news__content"}):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            url_relative = item.find("a").get("href")
            id_ = url_relative.replace("/", "_")
            feed_item["id"] = id_

            feed_item["title"] = self.clear_space_hyp(item.find("a").text)

            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, url_relative)

            time_data = self.clear_space_hyp(
                item.find("div", {"class": "e-news__date"}).text
            )

            timedata = time_data.split(" ")
            time_data = (
                timedata[2]
                + "."
                + Monats[timedata[1]]
                + "."
                + timedata[0]
                + " "
                + timedata[3]
            )
            time_fmt = "%Y.%m.%d %H:%M"
            feed_item["published_parsed"] = time.strptime(time_data, time_fmt)

            result["entries"].append(feed_item)
        return result


class MinVRParser(BaseParser):
    """
    Class to parse news from "https://minvr.gov.ru/press-center/news/" - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://minvr.gov.ru/press-center/news/"

    def parse(self, feed_url: str):
        result = {
            "feed": {
                "title": "min.vostok",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            print("soup is none")
            return result
        for item in soup.find_all("div", {"class": "card--flex"}):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }

            url_relative = item.find(
                "a", {"class": "article__link"}).get("href")
            id_ = url_relative.replace("/", "_")
            feed_item["id"] = id_

            feed_item["title"] = self.clear_space_hyp(
                item.find("a", {"class": "article__link"}).text)
            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, url_relative)

            time_data = item.find("span", {"class": "article__time"}).text
            if time_data.find(":") > 0:
                time_fmt = "%d.%m.%Y %H:%M"
            else:
                time_fmt = "%d.%m.%Y"
            feed_item["published_parsed"] = time.strptime(time_data, time_fmt)
            result["entries"].append(feed_item)
        return result


class MinTransParser(BaseParser):
    """
    Class to parse news from " https://mintrans.gov.ru/press-center/news" - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://mintrans.gov.ru/press-center/news"

    def parse(self, feed_url: str):
        result = {
            "feed": {
                "title": "mintrans",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            print("soup is none")
            return result

        for item in soup.find_all("div", {"class": "news-list-item"}):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            url_relative = item.find("a").get("href")
            id_ = url_relative.replace("/", "_")
            feed_item["id"] = id_

            feed_item["title"] = item.find(
                "a", {"class": "news-text"}).text.strip()
            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, url_relative)

            time_data = self.clear_space_hyp(
                item.find("span", {"class": "date-span"}).text
            )
            timedata = time_data.split(" ")
            if len(timedata[0]) == 1:
                timedata[0] = "0" + timedata[0]
            time_data = (
                timedata[2] + "." + Monats[timedata[1].lower()] +
                "." + timedata[0]
            )
            feed_item["published_parsed"] = time.strptime(
                time_data, "%Y.%m.%d")

            result["entries"].append(feed_item)
        return result


class EaeunionParser(BaseParser):
    """
    Class to parse news from "https://eec.eaeunion.org/news/" - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://eec.eaeunion.org/news/"

    def parse(self, feed_url: str):
        result = {
            "feed": {
                "title": "euraz.econ.com",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            print("soup is none")
            return result

        for item in soup.find_all("div", {"class": "news-pane-item"}):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            url_relative = item.find(
                "a", {"class": "news-pane-item__body"}).get("href")
            id_ = url_relative.replace("/", "_")
            feed_item["id"] = id_

            feed_item["title"] = item.find(
                "span", {"class": "news-pane-item__h"}
            ).text.strip()
            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, url_relative)
            a = item.find("span", {"class": "news-pane-item__date"}).text
            time_data = self.clear_space_hyp(
                item.find("span", {"class": "news-pane-item__date"}).text
            )

            timedata = time_data.split(" ")
            time_data = (
                timedata[2] + "." + Monats[timedata[1].lower()] +
                "." + timedata[0]
            )
            feed_item["published_parsed"] = time.strptime(
                time_data, "%Y.%m.%d")

            result["entries"].append(feed_item)
        return result

class PortNews(BaseParser):
    """
    Class to parse news from "https://portnews.ru/news" - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://portnews.ru/news/"

    def parse(self, feed_url: str):
        result = {
            "feed": {
                "title": "portnews",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            print("soup is none")
            return result
        block = soup.find_all(id="newsru")
        dates = block[0].find_all("h1")
        tables = block[0].find_all("table") 
        for i in range(len(dates)):
            for item in tables[i].find_all("tr"):
                feed_item = {
                    "title": None,
                    "published_parsed": None,
                    "link": None,
                    "id": None,
                }
                time_news = item.find_all("td")[0].text 
                url_relative = item.find("a").get("href")
                id_ = url_relative.replace("/", "_")
                feed_item["id"] = id_
                feed_item["title"] = item.find("a").text.strip()
                feed_item["link"] = urllib.parse.urljoin(self.url_base, url_relative)
                time_data = dates[i].text 
                timedata = time_data.split(" ")
                time_data = (timedata[2] + "." + Monats[timedata[1].lower()] +"." + timedata[0]) + " " + time_news
                feed_item["published_parsed"] = time.strptime(time_data, "%Y.%m.%d %H:%M")
                result["entries"].append(feed_item)
        return result   
    
class AhramParser(BaseParser):
    """
    Class to parse news from "https://english.ahram.org.eg/Portal/3/Business.aspx" - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://english.ahram.org.eg/Portal/3/Business.aspx"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.post(
            url, headers={"User-Agent": ua.random}, timeout=30, verify=False)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup    

    def parse(self, feed_url: str):
        result = {
            "feed": {
                "title": "ahram",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            print("soup is none")
            return result

        for item in soup.find_all("div", {"class": "col-md-6 col-lg-12 mar-top-outer"}):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            url_relative = item.find("a").get("href")
            id_ = url_relative.replace("/", "_")
            feed_item["id"] = id_

            feed_item["title"] = item.find("a").text.strip()
            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, url_relative)

            feed_item["published_parsed"]=struct_time(datetime.datetime.now().timetuple())

            result["entries"].append(feed_item)
        return result   

class AlBawaba(BaseParser):
    """
    Class to parse news from "https://www.albawaba.com/business" - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def __init__(self):
        self.url_base = "https://www.albawaba.com/business"

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.post(
            url, headers={"User-Agent": ua.random}, timeout=30, verify=False)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup    

    def parse(self, feed_url: str):
        result = {
            "feed": {
                "title": "al.bawada",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            print("soup is none")
            return result

        for item in soup.find_all("div", {"class": "field field--name-node-title field--type-ds field--label-hidden field--item"}):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            url_relative = item.find("a").get("href")
            id_ = url_relative.replace("/", "_")
            feed_item["id"] = id_

            feed_item["title"] = item.find("a").text.strip()
            feed_item["link"] = urllib.parse.urljoin(
                self.url_base, url_relative)

            feed_item["published_parsed"]=struct_time(datetime.datetime.now().timetuple())
            result["entries"].append(feed_item)
        return result 
    

class ArabTimes(BaseParser):
    """
    Class to parse news from "http://www.arabtimesonline.com" - no access to rss feed.
    Returns result with same fields which will be used later as feedparser result.
    """

    def get(self, url):
        """
        TODO: add retry when status_code != 200
        """
        ua = UserAgent()
        r = requests.post(
            url, headers={"User-Agent": ua.random}, timeout=30, verify=False)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.content.decode("utf-8"), features="html.parser")
        return soup    

    def parse(self, feed_url: str):
        result = {
            "feed": {
                "title": "arabtimes",
            },
            "href": feed_url,
            "entries": [],
        }

        soup = self.get(feed_url)
        if not soup:
            print("soup is none")
            return result

        for item in soup.find_all("article", {"class": "item-list"}):
            feed_item = {
                "title": None,
                "published_parsed": None,
                "link": None,
                "id": None,
            }
            item_1 = item.find("h2", {"class": "post-box-title"})
            url_relative = item_1.find("a").get("href")
            id_ = url_relative.replace("/", "_")
            feed_item["id"] = id_

            feed_item["title"] = item_1.find("a").text.strip()

            feed_item["link"] = item_1.find("a").get("href")
            
            feed_item["published_parsed"]=struct_time(datetime.datetime.now().timetuple())

            result["entries"].append(feed_item)
        return result        

class No_Parse:
    def parse(self, feed_url):
        pass


ParserByName = {
    "AfricabusinesscommunitiesParser": AfricabusinesscommunitiesParser(),
    "AfricanewsParser": AfricanewsParser(),
    "AgroobzorParser": AgroobzorParser(),
    "AhramParser": AhramParser(),
    "AlBawaba": AlBawaba(),
    "ArabTimes": ArabTimes(),
    "APKInformParser": APKInformParser(),
    "APNewsParser": APNewsParser(),
    "CDUParser": CDUParser(),
    "CGTNParser": CGTNParser(),
    "CommerceGovInParser": CommerceGovInParser(),
    "CommonParser": CommonParser(),
    "CRIParser": CRIParser(),
    "EaeunionParser": EaeunionParser(),
    "ExportcenterParser": ExportcenterParser(),
    "IQNAParser": IQNAParser(),
    "JapanNewsParser": JapanNewsParser(),
    "MetalBulletinParser": MetalBulletinParser(),
    "MilknewsParser": MilknewsParser(),
    "MinEconDevelParser": MinEconDevelParser(),
    "MinTransParser": MinTransParser(),
    "MinVRParser": MinVRParser(),
    "MOFAJapanParser": MOFAJapanParser(),
    "MofcomParser": MofcomParser(),
    "MontsameParser": MontsameParser(),
    "NGVParser": NGVParser(),
    "no parser": No_Parse(),
    "PortNews": PortNews(),
    "ReutersParser": ReutersParser(),
    "RuChinaParser": RuChinaParser(),
    "ThedticParser": ThedticParser(),
    "TorgPredParser": TorgPredParser(),
    "USDepartmentOfTreasuryParser": USDepartmentOfTreasuryParser(),
    "XinhuaParser": XinhuaParser(),
}


class FeedDownloader:
    """
    Main class for feed downloads and database updates.
    Used in cron jobs for periodical updates.
    """

    def __init__(self):
        # self.feed_urls = feed_urls
        self.rss_raw = {}

        # Session = sessionmaker(engine)
        self.session = Session(bind=engine)

    def get_datetime(self, delta=0):
        return (
            datetime.datetime.now(datetime.timezone.utc) +
            datetime.timedelta(delta)
        ).replace(hour=0, minute=0, second=0, microsecond=0)

    def get_feeds(self):
        feeds_count = 0
        warnings.filterwarnings("ignore", message="Unverified HTTPS request")
        try:
            data = (
                select(Feed)
                .where(
                    Feed.used == True,
                    Feed.available == True,
                    Feed.parser_name != "no parser",
                )
                .order_by(Feed.name)
            )
            print("Parsing feeds\n")
            for feed in self.session.scalars(data):
                try:
                    if feed.parser_name != "no parser":
                        if feed.parser_name in ParserByName:
                            parser = ParserByName[feed.parser_name]
                            feed_cur = parser.parse(feed.url)
                            self.rss_raw[feed.name] = feed_cur
                            feeds_count += 1
                            print(
                                f"{feed.name} - id={feed.id}, site: {feed.url}  Ok")
                        else:
                            print(
                                f"Parser with name {feed.parser_name} not found")
                            continue
                    else:
                        continue
                except Exception as e:
                    print(f"ERROR <{feed.name}> {e}")
        except Exception as e:
            print("ERROR ", feed.name, e)

        print("Done parsing feeds\n")
        return feeds_count

    def get_articles(self):
        """
        Update feeds article data.
        """
        # Добавлен фильтр в диапазоне дат  месяц
        start_date = self.get_datetime(-DELTA_DATE_ARTICLE)
        end_date = self.get_datetime(1)

        feeds_count = self.get_feeds()

        if feeds_count > 0:
            count_news = 0
            count_news_excluded=0
            try:
                for feed in self.rss_raw:
                    print(feed)
                    new_articles_count=0
                    news_excluded=0
                    for article in self.rss_raw[feed]["entries"]:
                        if article:
                            feed_name = feed
                            feed_id = self.session.scalars(
                                select(Feed.id).where(Feed.name == feed_name)
                            ).first()

                            try:
                                if feed in ["rbc", "aif"]:
                                    url = article["links"][0]["href"]
                                else:
                                    url = article["link"]

                                id_in_feed = article.get("id", url)

                                if not id_in_feed:
                                    id_in_feed = url
                                id_in_feed = id_in_feed[-400:]
                                title = article["title"]
                                title = title.replace('"', "")
                            except Exception as e:
                                print(e)
                                continue

                            if article.get("published_parsed"):
                                published_parsed = datetime.datetime.fromtimestamp(
                                    mktime(article["published_parsed"]),
                                    tz=pytz.timezone("UTC"),
                                )
                                if published_parsed.month == 1:
                                    if is_leap_year(published_parsed.year):
                                        nums_days = 29
                                else:
                                    nums_days = month_days[published_parsed.month - 1]

                                if (
                                    published_parsed.hour >= 21
                                    and published_parsed.day == nums_days
                                ):
                                    published_parsed = published_parsed.replace(
                                        hour=20)
                            else:
                                published_parsed = datetime.datetime.now(
                                    tz=pytz.timezone("UTC")
                                )

                            try:
                                # Фильтр в диапазоне дат
                                if (published_parsed >= start_date and published_parsed <= end_date):
                                    # Фильтр по стоп-словам
                                    if check_stop_words(title):    
                                            #проверка наличия новости
                                            new_article = self.session.scalars(
                                                select(Article).where(
                                                    Article.feed_id == feed_id,
                                                    # Article.id_in_feed == id_in_feed,
                                                    # Article.url == url,
                                                    Article.title == title,
                                                    Article.published_parsed >= start_date,
                                                    Article.published_parsed <= end_date,
                                                )
                                            )
                                            if not new_article.first() and title.find('Ð') < 0: 
                                                self.session.add(
                                                    Article(
                                                        id_in_feed=id_in_feed,
                                                        url=url[-2048:],
                                                        title=title,
                                                        # title_json=None,
                                                        is_entities_parsed=False,
                                                        feed_id=feed_id,
                                                        published_parsed=published_parsed,
                                                        is_text_parsed=False,
                                                    )
                                                )
                                                new_articles_count += 1
                                            else:
                                                continue
                                    else: 
                                        exlcude_news = self.session.scalars(
                                            select(ExcludedFilter).where(
                                            ExcludedFilter.title==title,
                                            ExcludedFilter.published_parsed==published_parsed,
                                            ExcludedFilter.url==url,
                                            ))
                                        if not exlcude_news.first():
                                            self.session.add(
                                                ExcludedFilter(
                                                title=title,
                                                url=url[-2048:],
                                                published_parsed=published_parsed,
                                                ))
                                            news_excluded+=1
                                            
                                        else:
                                            continue
                                else:
                                    continue
                                self.session.commit()
                            except Exception as e:
                                self.session.rollback()
                                print(feed, e, article)
                    print(new_articles_count)
                    count_news = count_news + new_articles_count
                    count_news_excluded= count_news_excluded +news_excluded
            finally:
                print("*" * 80)
                print(f"Searched {feeds_count} news sites and rss feeds")
                print(
                    f"{count_news} news added to the table newsfeedner_article for the current session."
                )
                print(
                    f"{count_news_excluded} excluded by filter for the current session."
                )
        self.session.close()
