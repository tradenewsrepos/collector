import time
import datetime
from config import get_time, DOWNLOAD_TEXT_SLEEP
from download_text import FeedTextDownloader


if __name__ == '__main__':
    while True:
        # time.sleep(300)
        starttime = time.time()
        print('*'*80 + '\n' + 'downloader = FeedTextDownloader()' + '\n' + '*'*80)
        downloader = FeedTextDownloader()
        print('*'*80 + '\n' + get_time() + ' Start get_texts()' + '\n' + '*'*80)
        downloader.get_texts()
        endtime = time.time()
        print(f'Service worked {(endtime-starttime)//60} min')

        print('*'*80 + '\n' + 'Done get_texts()' + '\n' + '*'*80)
        print(f'Sleeping for {DOWNLOAD_TEXT_SLEEP//60} min ')
        print('='*80)
        time.sleep(DOWNLOAD_TEXT_SLEEP)
