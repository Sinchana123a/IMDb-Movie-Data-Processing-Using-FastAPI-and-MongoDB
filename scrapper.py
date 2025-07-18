import requests
from bs4 import BeautifulSoup
from pymongo import MongoClient
import re
import json


def split_cast(paragraphs):
    for p in paragraphs:
        if 'Stars:' in p.text:
            text = p.text.strip()
            idx = text.find('Stars:')
            cast_string = text[idx + 6:].split('|')[0].strip()
            return [name.strip() for name in cast_string.split(',')]
    return []


def extract_movies_from_jsonld(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    scripts = soup.find_all("script", type="application/ld+json")

    movie_data = []
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict) and data.get('@type') == 'ItemList':
                for item in data.get('itemListElement', []):
                    movie = item['item']
                    movie_data.append({
                        'id': movie['url'].split('/')[4],
                        'movie_name': movie['name'],
                        'genre': movie['genre'].split(', ') if isinstance(movie['genre'], str) else movie['genre'],
                        'runtime': movie['duration'],
                        'rating': float(movie['aggregateRating']['ratingValue']) if 'aggregateRating' in movie else None,
                        'url': movie['url']
                    })
        except Exception as e:
            print("[!] Failed to parse JSON-LD:", e)

    return movie_data


def enrich_with_cast(html_text, movie_list):
    """
    Uses fallback HTML scraping to find cast from <p> tags.
    Assumes movie_list is ordered as per page appearance.
    """
    soup = BeautifulSoup(html_text, "html.parser")
    containers = soup.select('div.lister-item-content')

    print("[*] Attempting cast extraction via fallback HTML parsing...")
    for idx, container in enumerate(containers):
        try:
            paragraphs = container.find_all("p")
            cast = split_cast(paragraphs)
            if idx < len(movie_list):
                movie_list[idx]['cast'] = cast
        except Exception as e:
            print(f"[!] Error extracting cast for index {idx}: {e}")
            movie_list[idx]['cast'] = []
    return movie_list


def insert_to_mongodb(data):
    if not data:
        print("[!] No data to insert. Skipping MongoDB insertion.")
        return

    client = MongoClient('mongodb+srv://sahana:sahana-123@cluster0.hl7kiqb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
    db = client['IMDB']
    collection = db['movies_data']

    print("[*] Inserting into MongoDB...")
    collection.delete_many({})
    collection.insert_many(data)
    print(f"[✓] Inserted {len(data)} documents into MongoDB.")


def main():
    headers = {"User-Agent": "Mozilla/5.0"}
    all_movies = []

    for i in range(1, 11):  # Change range(1, 11) for full scrape
        url = f"https://www.imdb.com/list/ls006266261/?sort=user_rating,desc&mode=detail&page={i}"
        print(f"[+] Fetching page {i}: {url}")
        response = requests.get(url, headers=headers)
        if not response.ok:
            print(f"[!] Failed to fetch page {i}")
            continue

        movies = extract_movies_from_jsonld(response.text)
        movies = enrich_with_cast(response.text, movies)
        print(f"[✓] Page {i} - Extracted {len(movies)} movies.")
        all_movies.extend(movies)

    print(f"\n[*] Total Movies Scraped: {len(all_movies)}")
    if all_movies:
        print("[>] Sample Movie:", all_movies[0])

    insert_to_mongodb(all_movies)

    # Optional: View inserted data
    print("[*] Fetching back some entries from MongoDB...")
    client = MongoClient('mongodb+srv://sahana:sahana-123@cluster0.hl7kiqb.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
    for doc in client.IMDB.movies_data.find().limit(5):
        print(doc)


if __name__ == "__main__":
    main()
