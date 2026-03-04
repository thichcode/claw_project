import urllib.request
import xml.etree.ElementTree as ET
import datetime
import email.utils

feeds = {
    'Reuters World': 'https://feeds.reuters.com/Reuters/worldNews',
    'BBC World': 'http://feeds.bbci.co.uk/news/world/rss.xml',
    'NYT World': 'https://rss.nytimes.com/services/xml/rss/nyt/World.xml',
    'Guardian World': 'https://www.theguardian.com/world/rss',
    'Al Jazeera': 'https://www.aljazeera.com/xml/rss/all.xml',
}

now = datetime.datetime.now(datetime.timezone.utc)
for name, url in feeds.items():
    print(f"\n## {name} {url}")
    try:
        data = urllib.request.urlopen(url, timeout=20).read()
        root = ET.fromstring(data)
        items = root.findall('.//item')[:10]
        print('items', len(items))
        for it in items:
            title = (it.findtext('title') or '').strip().replace('\n', ' ')
            link = (it.findtext('link') or '').strip()
            pd = (it.findtext('pubDate') or '').strip()
            age = 'NA'
            if pd:
                try:
                    dt = email.utils.parsedate_to_datetime(pd)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=datetime.timezone.utc)
                    age = f"{int((now - dt.astimezone(datetime.timezone.utc)).total_seconds()/60)}m"
                except Exception:
                    pass
            print(f"- {title[:120]} | {age} | {link}")
    except Exception as e:
        print('ERROR', e)
