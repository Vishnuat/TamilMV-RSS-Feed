import os
import requests
import pickle
from bs4 import BeautifulSoup
from datetime import datetime
import xml.etree.ElementTree as ET
from flask import Flask, send_file, Response
from functools import lru_cache
from threading import Thread
from time import sleep
import itertools
import concurrent.futures
from pymongo import MongoClient, errors


class Scraper:
    def __init__(self):
        self.url = os.environ.get('SCRAPER_URL', 'https://www.1tamilmv.se/')
        self.port = int(os.environ.get("PORT", 8000))

        # --- MongoDB INIT ---
        mongo_uri = os.environ.get("MONGODB_URI", "mongodb+srv://bahov19860:RY4Qz3jtp9NXqkUS@cluster0.zztswen.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
        self.client = MongoClient(mongo_uri)
        self.db = self.client["rssfeed"]
        self.collection = self.db["feeds"]
        self.collection.create_index("link", unique=True)

        # --- Flask App ---
        self.app = Flask(__name__)
        self.setup_routes()

        # --- Threads to run app and schedule ---
        Thread(target=self.begin).start()
        Thread(target=self.run_schedule).start()

    @lru_cache(maxsize=128)
    def get_links(self, url):
        """Extracts all attachment links from a given thread URL."""
        try:
            response = requests.get(url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            a_tags = soup.find_all('a', href=lambda href: href and 'attachment.php' in href)
            return a_tags
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            return []

    def get_links_with_delay(self, link):
        result = self.get_links(link)
        sleep(2)
        return result

    def scrape(self, links):
        """Scrape the attachment links from given forum threads."""
        with concurrent.futures.ThreadPoolExecutor() as executor:
            results = executor.map(self.get_links_with_delay, itertools.islice(links, 30))
            for result in results:
                for a in result:
                    yield a.text.strip(), a['href']

    def fetch_links_from_homepage(self):
        """Extracts forum thread links from homepage."""
        try:
            response = requests.get(self.url, timeout=10)
            soup = BeautifulSoup(response.content, 'html.parser')
            paragraphs = soup.find_all('p', style='font-size: 13.1px;')
            links = [a['href'] for p in paragraphs for a in p.find_all('a', href=True)]
            return [link for link in links if 'index.php?/forums/topic/' in link]
        except Exception as e:
            print(f"Error parsing homepage: {e}")
            return []

    def begin(self):
        """Initial scraping (if MongoDB is empty) and RSS creation."""
        if self.collection.count_documents({}) > 0:
            print("MongoDB already contains data. Skipping initial scrape.")
            return

        print("Starting initial scrape...")
        thread_links = self.fetch_links_from_homepage()
        scraped = list(self.scrape(thread_links))
        documents = [
            {"title": title, "link": link, "pubDate": datetime.now().isoformat()}
            for title, link in scraped
        ]

        try:
            self.collection.insert_many(documents, ordered=False)
            print(f"Inserted {len(documents)} items into MongoDB.")
        except errors.BulkWriteError as bwe:
            print("Some duplicate items may already exist:", bwe.details)

        self.generate_rss_file()

    def job(self):
        """Scheduled job to check for new items every ~25 min."""
        print("Running scheduled job...")
        thread_links = self.fetch_links_from_homepage()
        scraped = list(self.scrape(thread_links))

        existing_links = set(
            doc["link"] for doc in self.collection.find({}, {'link': 1})
        )
        new_links = [item for item in scraped if item[1] not in existing_links]

        if new_links:
            print(f"New items found: {len(new_links)}")
            docs = [
                {"title": title, "link": link, "pubDate": datetime.now().isoformat()}
                for title, link in new_links
            ]
            try:
                self.collection.insert_many(docs, ordered=False)
            except errors.BulkWriteError:
                pass
            self.generate_rss_file()
        else:
            print("No new items found.")

    def run_schedule(self):
        while True:
            sleep(60)
            self.job()

    def generate_rss_file(self):
        """Generates the RSS XML file from MongoDB's latest 10 entries."""
        rss = ET.Element('rss', version='2.0')
        channel = ET.SubElement(rss, 'channel')
        ET.SubElement(channel, 'title').text = 'TamilMV RSS Feed'
        ET.SubElement(channel, 'description').text = 'Share and support'
        ET.SubElement(channel, 'link').text = 'https://t.me/VC_Movie'

        records = list(self.collection.find().sort("pubDate", -1).limit(10))
        for doc in records:
            item = ET.SubElement(channel, 'item')
            ET.SubElement(item, 'title').text = doc.get('title')
            ET.SubElement(item, 'link').text = doc.get('link')
            ET.SubElement(item, 'pubDate').text = doc.get('pubDate', datetime.now().isoformat())

        tree = ET.ElementTree(rss)
        tree.write('tamilmvRSS.xml', encoding='utf-8', xml_declaration=True)
        print("RSS feed updated with latest 10 items.")

    def setup_routes(self):
        @self.app.route("/")
        def serve_rss():
            return send_file('tamilmvRSS.xml')

        @self.app.route("/status")
        def status():
            return Response("Scraper is running", status=200)

    def run(self):
        print(f"Flask server running on port {self.port}")
        self.app.run(host="0.0.0.0", port=self.port)


if __name__ == '__main__':
    scraper = Scraper()
    scraper.run()
