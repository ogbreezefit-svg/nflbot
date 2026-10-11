import unittest

from news_stats import normalize_news, link_news


class NewsProvenanceTests(unittest.TestCase):
    def article(self, **changes):
        item = {
            "link": "https://example.com/synthetic-news",
            "title": "Test Receiver: Reported update.",
        }
        item.update(changes)
        return item

    def normalize(self, item):
        return normalize_news({
            "statusCode": 200,
            "body": [item],
        })[0]

    def test_original_provider_fields_are_preserved(self):
        item = self.article(
            playerID="synthetic-player",
            image="https://example.com/image.png",
        )
        article = self.normalize(item)

        self.assertEqual(article["source_provider"], "Tank01")
        self.assertEqual(article["source_endpoint"], "getNFLNews")
        self.assertEqual(article["source_record"], item)
        self.assertIsNot(article["source_record"], item)
        self.assertIsNone(article["published_at"])
        self.assertEqual(
            article["publication_time_status"], "UNVERIFIED"
        )
        self.assertFalse(article["availability_verified"])

    def test_unknown_date_field_is_not_treated_as_verified_time(self):
        item = self.article(
            date="synthetic-undocumented-date",
            playerIDs=["synthetic-player"],
        )
        article = self.normalize(item)

        self.assertEqual(article["source_record"]["date"], item["date"])
        self.assertEqual(
            article["source_record"]["playerIDs"],
            ["synthetic-player"],
        )
        self.assertIsNone(article["published_at"])
        self.assertEqual(
            article["publication_time_status"], "UNVERIFIED"
        )

    def test_linking_retains_provenance_without_verifying_availability(self):
        article = self.normalize(self.article(
            playerID="synthetic-player"
        ))
        linked, unmatched = link_news([article], [{
            "player_id": "synthetic-player",
            "name": "Test Receiver",
            "team_abv": "TEST",
        }])

        self.assertEqual(unmatched, 0)
        result = linked["TEST"][0]
        self.assertEqual(result["source_record"], article["source_record"])
        self.assertEqual(result["match_method"], "unique_exact_name")
        self.assertIsNone(result["published_at"])
        self.assertFalse(result["availability_verified"])


if __name__ == "__main__":
    unittest.main()
