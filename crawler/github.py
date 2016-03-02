"""
Github Crawler

Polls the github api retrieving all public repository urls. Once found, they are stored in the
algthm.repositories.
"""

from urlparse import urljoin
from crawler.cfg.loader import cfg
from crawler.core.db import MongoConnection
from crawler.logger import logger
import requests
from pymongo.errors import DuplicateKeyError

logger = logger.get_logger(__name__)

class GitHub(object):

    GITHUB_API_BASE = 'https://api.github.com/'
    REPO_NAME = 'full_name'
    ENDPOINTS = dict(
        repositories=urljoin(GITHUB_API_BASE, 'repositories')
    )
    GITHUB_BASE = 'https://github.com/'

    #	Flag to stop processing
    __run = True

    # The repositories endpoint takes in a since parameter which it will return
    # results from this point. It refers to the repository ID. It is paginated
    # so we must call the API each time with the last repository ID we've seen.
    # This value is fetched from the `state` table algthm database as it is 
    # updated upon every api response.
    position = None

    connection = None

    def __init__(self):
        self.connection = MongoConnection().get_db()
        self.get_position()

    def __exit__(self):
        self.cursor.close()

    def get_position(self):
        self.position = self.connection.crawler_position.find_one()
        if not self.position:
            _id = self.connection.crawler_position.insert({
                'discovery_since': 0
            })
            self.position = self.connection.crawler_position.find_one({'_id': _id})

    def save_position(self, discovery_since):
        self.connection.crawler_position.update({
                '_id': self.position['_id']
            },{
                '$set': {
                    'discovery_since': discovery_since,
                }
            }, upsert=False, multi=True)
        self.position['discovery_since'] = discovery_since

    def run(self):
        while self.__run:
            auth_header = {'Authorization': ('token {}'.format(cfg.settings.github.auth))}
            res = requests.get(self.construct_url(), headers=auth_header)
            self.process_response(res)

    def construct_url(self):
        url = "{}?{}={}".format(self.ENDPOINTS['repositories'], 'since', self.position['discovery_since'])
        return url

    def process_response(self, response):
        if response.status_code != 404 or response.status_code != 500:
            repos = response.json()
            if len(repos):
                for repo in repos:
                    self.insert_to_db(urljoin(self.GITHUB_BASE, repo[self.REPO_NAME]))

                self.save_position(repos[-1]['id'])
            else:
                #	Stop running on empty response
                self.__run = False

        logger.info('\033[1;36mCrawling\033[0m {} repositories discovered ..'.format(self.position['discovery_since']))

    def insert_to_db(self, url):
        print '> found {}'.format(url)
        try:
            self.connection.repositories.insert({'url': url, 'state': 0, 'error_count': 0})
        except DuplicateKeyError:
            pass

github = GitHub()
