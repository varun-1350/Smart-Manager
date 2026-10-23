import urllib.parse
import webbrowser
from urllib.parse import urlparse
from typing import Dict, Any


class BrowserOperations:
    @staticmethod
    def search_web(query: str) -> Dict[str, Any]:
        encoded = urllib.parse.quote_plus(query.strip())
        search_url = f"https://www.google.com/search?q={encoded}"
        webbrowser.open(search_url)
        return {
            "action": "search_web",
            "query": query,
            "url": search_url,
            "browser_opened": True,
        }

    @staticmethod
    def open_url(url: str) -> Dict[str, Any]:
        cleaned = url.strip()
        parsed = urlparse(cleaned)
        if not parsed.scheme and cleaned and "://" not in cleaned:
            cleaned = "https://" + cleaned
            parsed = urlparse(cleaned)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Only absolute HTTP(S) URLs can be opened.")

        webbrowser.open(cleaned)
        return {
            "action": "open_url",
            "url": cleaned,
            "browser_opened": True,
        }

    @staticmethod
    def play_youtube(query: str) -> Dict[str, Any]:
        encoded = urllib.parse.quote_plus(query.strip())
        youtube_url = f"https://www.youtube.com/results?search_query={encoded}"
        webbrowser.open(youtube_url)
        return {
            "action": "play_youtube",
            "query": query,
            "url": youtube_url,
            "browser_opened": True,
        }
