import time
import datetime
from config import get_time, DOWNLOAD_ARTICLE_SLEEP
from download_article import FeedDownloader

if __name__ == '__main__':
    while True:
        starttime = time.time()
        print('*'*80 + '\n' + get_time() +
              ' - downloader = FeedDownloader()' + '\n' + '*'*80)
        downloader = FeedDownloader()
        print('*'*80 + '\n' + 'downloader.get_articles()' + '\n' + '*'*80)
        downloader.get_articles()
        endtime = time.time()
        print(f'Service worked {(endtime-starttime)//60} min')
        print('*'*80 + '\n' + 'Done get_articles()' + '\n' + '*'*80)
        print(f' Sleeping for {DOWNLOAD_ARTICLE_SLEEP//60}  min')
        print('='*80)
        time.sleep(DOWNLOAD_ARTICLE_SLEEP)
