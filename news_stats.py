"""Pure news validation and conservative player-name matching."""
import hashlib
from urllib.parse import urlparse


class NoNewsResults(ValueError):
    pass


def normalize_news(payload):
    if not isinstance(payload, dict):
        raise ValueError("News payload must be an object")
    if str(payload.get("statusCode")) != "200":
        raise ValueError("Provider status unsuccessful")

    error = payload.get("error")
    if error:
        if str(error).strip().casefold() == "your query returned no results.":
            raise NoNewsResults("Provider returned no results")
        raise ValueError("Provider reported an error")

    body = payload.get("body")
    if not isinstance(body, list):
        raise ValueError("News body must be a list")
    if not body:
        raise NoNewsResults("News feed empty")

    articles = {}
    for item in body:
        if not isinstance(item, dict):
            raise ValueError("Invalid news record")

        link, title = item.get("link"), item.get("title")
        if not isinstance(link, str) or not isinstance(title, str):
            raise ValueError("News link/title missing")

        link, title = link.strip(), title.strip()
        parsed = urlparse(link)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or not title:
            raise ValueError("Invalid news link/title")

        candidate, separator, remainder = title.partition(":")
        candidate = candidate.strip() if separator and remainder.strip() else None

        article_id = hashlib.sha256(
            (link + "\n" + title).encode("utf-8")
        ).hexdigest()

        articles[article_id] = {
            "article_id": article_id,
            "link": link,
            "title": title,
            "candidate_player_name": candidate,
            "published_at": None,
            "availability_verified": False,
        }

    return list(articles.values())


def name_key(value):
    return " ".join(str(value or "").split()).casefold()


def link_news(articles, roster):
    index = {}
    for player in roster:
        key = name_key(player.get("name"))
        if not key:
            continue
        identity = (str(player["player_id"]), player["team_abv"])
        index.setdefault(key, {})[identity] = player

    by_team = {}
    unmatched = 0

    for article in articles:
        matches = index.get(name_key(article.get("candidate_player_name")), {})
        if len(matches) != 1:
            unmatched += 1
            continue

        player = next(iter(matches.values()))
        linked = dict(article)
        linked["matched_player_id"] = str(player["player_id"])
        linked["match_method"] = "unique_exact_name"
        by_team.setdefault(player["team_abv"], []).append(linked)

    return by_team, unmatched
