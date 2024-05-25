import requests
from bs4 import BeautifulSoup
import torrent_parser as tp
import xml.etree.ElementTree as ET
from datetime import datetime 
import itertools
from time import sleep
import concurrent.futures
import pickle
from flask import Flask, send_file, Response
import os
from threading import Thread
from functools import lru_cache

class Scraper:
    def __init__(self):
        self.all_links = []
        self.titles = []
        self.url = 'https://www.1tamilmv.eu/'
        self.port = int(os.environ.get("PORT", 8000))
        self.app = Flask(__name__)
        self.setup_routes()
        self.start_threads()

    def start_threads(self):
        Thread(target=self.begin, daemon=True).start()
        Thread(target=self.run_schedule, daemon=True).start()

    def save_list_to_file(self):
        try:
            with open('rssList.txt', 'wb') as f:
                pickle.dump(self.all_links, f)
        except Exception as e:
            print(f"Error saving list to file: {e}")

    def load_list_from_file(self):
        try:
            with open('rssList.txt', 'rb') as f:
                self.all_links = pickle.load(f)
                self.titles = [link[0] for link in self.all_links]
        except Exception as e:
            print(f"Error loading list from file: {e}")

    @lru_cache(maxsize=128)
    def get_links(self, url):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')
            a_tags = soup.find_all('a', href=lambda href: href and 'attachment.php' in href)
            return a_tags
        except requests.RequestException as e:
            print(f"Error fetching links: {e}")
            return []

    def get_torrent_size(self, torrent_file_path):
        try:
            data = tp.parse_torrent_file(torrent_file_path)
            if 'files' in data['info']:
                size = sum(file['length'] for file in data['info']['files'])
            else:
                size = data['info']['length']
            return size
        except Exception as e:
            print(f"Error parsing torrent file: {e}")
            return 0

    def get_links_with_delay(self, link):
        result = self.get_links(link)
        sleep(5)  # Introduce a delay of 5 seconds between each request
        return result

    def scrape(self, links):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(self.get_links_with_delay, itertools.islice(links, 30))
            for result in results:
                for a in result:
                    yield a.text, a['href']

    def build_xml(self, channel):
        now = datetime.now()
        for x in self.all_links:
            item = ET.SubElement(channel, 'item')
            ET.SubElement(item, 'title').text = x[0]
            ET.SubElement(item, 'link').text = x[1]
            ET.SubElement(item, 'pubDate').text = now.isoformat('T')

    def begin(self):
        if os.path.exists('rssList.txt'):
            self.load_list_from_file()
            print("rssList.txt loaded")
            return
        print('Feed generation started')
        rss = ET.Element('rss', version='2.0')
        channel = ET.SubElement(rss, 'channel')
        ET.SubElement(channel, 'title').text = 'TamilMV RSS'
        ET.SubElement(channel, 'description').text = 'Share and support'
        ET.SubElement(channel, 'link').text = 'https://instagram.com/mr.anonymous.wiz'

        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            content = response.content
            soup = BeautifulSoup(content, 'html.parser')

            paragraphs = soup.find_all('p', style='font-size: 13.1px;')

            links = [a['href'] for p in paragraphs for a in p.find_all('a', href=True)]
            filtered_links = [link for link in links if 'index.php?/forums/topic/' in link]
            self.all_links = list(self.scrape(filtered_links))
            self.titles = [link[0] for link in self.all_links]
            self.save_list_to_file()

            self.build_xml(channel)

            tree = ET.ElementTree(rss)
            tree.write('tamilmvRSS.xml', encoding='utf-8', xml_declaration=True)
            print('Base feed finished')
        except requests.RequestException as e:
            print(f"Error initializing: {e}")

    def job(self):
        if len(self.all_links) == 0:
            if os.path.exists('rssList.txt'):
                self.load_list_from_file()
        print('Fetching Started')
        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            content = response.content
            soup = BeautifulSoup(content, 'html.parser')

            paragraphs = soup.find_all('p', style='font-size: 13.1px;')

            links = [a['href'] for p in paragraphs for a in p.find_all('a', href=True)]
            filtered_links = [link for link in links if 'index.php?/forums/topic/' in link]

            scraped = list(self.scrape(filtered_links))

            new_links = [link for link in scraped if link[0] not in self.titles]

            self.all_links = new_links + self.all_links

            if len(new_links):
                self.save_list_to_file()
                tree = ET.ElementTree()
                tree.parse('tamilmvRSS.xml')

                root = tree.getroot()
                channel = root.find('channel')
                npw = datetime.now().isoformat()
                for item_data in reversed(new_links):
                    item = ET.Element('item')
                    ET.SubElement(item, 'title').text = item_data[0]
                    ET.SubElement(item, 'link').text = item_data[1]
                    ET.SubElement(item, 'pubDate').text = npw
                    channel.insert(3, item)
                tree.write('tamilmvRSS.xml', encoding='utf-8', xml_declaration=True)
                print('New items added to feed')
        except requests.RequestException as e:
            print(f"Error during job execution: {e}")

    def run_schedule(self):
        while True:
            self.job()
            sleep(1500)

    def run(self):
        print(f"Server is running on port {self.port}")
        self.app.run(host='0.0.0.0', port=self.port)

    def setup_routes(self):
        @self.app.route('/')
        def serve_rss():
            return send_file('tamilmvRSS.xml')

        @self.app.route('/status')
        def start():
            return Response("Server is running", status=200)

if __name__ == '__main__':
    scraper = Scraper()
    scraper.run()
