import unittest
from news_stats import normalize_news, link_news, NoNewsResults


class NewsStatsTests(unittest.TestCase):
    def payload(self, items):
        return {"statusCode": 200, "body": items}

    def article(self, name="Test Receiver", link="https://example.com/update"):
        return {"link": link, "title": f"{name}: Reported update."}

    def test_valid_article(self):
        article = normalize_news(self.payload([self.article()]))[0]
        self.assertEqual(article["candidate_player_name"], "Test Receiver")
        self.assertIsNone(article["published_at"])
        self.assertFalse(article["availability_verified"])

    def test_exact_duplicates_removed(self):
        result = normalize_news(self.payload([self.article(), self.article()]))
        self.assertEqual(len(result), 1)

    def test_same_link_different_players_preserved(self):
        result = normalize_news(self.payload([
            self.article("Test Receiver"),
            self.article("Other Receiver"),
        ]))
        self.assertEqual(len(result), 2)

    def test_no_results_not_success(self):
        with self.assertRaises(NoNewsResults):
            normalize_news({
                "statusCode": 200,
                "error": "Your query returned no results.",
                "body": [],
            })

    def test_empty_feed_not_success(self):
        with self.assertRaises(NoNewsResults):
            normalize_news(self.payload([]))

    def test_invalid_link_rejected(self):
        with self.assertRaises(ValueError):
            normalize_news(self.payload([
                self.article(link="javascript:bad"),
            ]))

    def test_unique_name_match(self):
        articles = normalize_news(self.payload([self.article()]))
        linked, unmatched = link_news(articles, [{
            "player_id": "synthetic-id",
            "name": "Test Receiver",
            "team_abv": "TEST",
        }])
        self.assertEqual(unmatched, 0)
        self.assertEqual(linked["TEST"][0]["matched_player_id"], "synthetic-id")

    def test_ambiguous_name_not_linked(self):
        articles = normalize_news(self.payload([self.article()]))
        linked, unmatched = link_news(articles, [
            {"player_id": "1", "name": "Test Receiver", "team_abv": "ONE"},
            {"player_id": "2", "name": "Test Receiver", "team_abv": "TWO"},
        ])
        self.assertEqual(linked, {})
        self.assertEqual(unmatched, 1)

    def test_unmatched_name_not_guessed(self):
        articles = normalize_news(self.payload([self.article()]))
        linked, unmatched = link_news(articles, [{
            "player_id": "1",
            "name": "Different Receiver",
            "team_abv": "TEST",
        }])
        self.assertEqual(linked, {})
        self.assertEqual(unmatched, 1)


if __name__ == "__main__":
    unittest.main()
