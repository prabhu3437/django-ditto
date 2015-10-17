from django.test import TestCase

from .. templatetags import twitter

from ..factories import AccountFactory, TweetFactory, UserFactory
from ..templatetags import twitter


class TemplatetagsRecentTweetsTestCase(TestCase):

    def setUp(self):
        user_1 = UserFactory(screen_name='terry')
        user_2 = UserFactory(screen_name='bob', is_private=True)
        user_3 = UserFactory(screen_name='thelma')
        account_1 = AccountFactory(user=user_1)
        account_2 = AccountFactory(user=user_2)
        account_3 = AccountFactory(user=user_3)
        self.tweets_1 = TweetFactory.create_batch(2, user=user_1)
        self.tweets_2 = TweetFactory.create_batch(3, user=user_2)
        self.tweets_3 = TweetFactory.create_batch(4, user=user_3)

    def test_recent_tweets(self):
        "Returns recent tweets from all public accounts"
        tweets = twitter.recent_tweets()
        self.assertEqual(6, len(tweets))
        # tweets[4] would be self.tweets_2[2] if user_2 wasn't private.
        self.assertEqual(tweets[4].pk, self.tweets_1[1].pk)

    def test_recent_tweets_account(self):
        "Returns recent tweets from one public account"
        tweets = twitter.recent_tweets(screen_name='terry')
        self.assertEqual(2, len(tweets))
        self.assertEqual(tweets[0].pk, self.tweets_1[1].pk)

    def test_recent_tweets_private_account(self):
        "Returns no tweets from a private account"
        tweets = twitter.recent_tweets(screen_name='bob')
        self.assertEqual(0, len(tweets))

    def test_recent_tweets_limit(self):
        tweets = twitter.recent_tweets(limit=5)
        self.assertEqual(5, len(tweets))
        self.assertEqual(tweets[4].pk, self.tweets_1[1].pk)


class TemplatetagsRecentFavoritesTestCase(TestCase):

    def setUp(self):
        user_1 = UserFactory(screen_name='terry')
        user_2 = UserFactory(screen_name='bob')
        account_1 = AccountFactory(user=user_1)
        account_2 = AccountFactory(user=user_2)

        tweets = TweetFactory.create_batch(6)
        account_1.user.favorites.add(tweets[1])
        account_1.user.favorites.add(tweets[3])
        account_2.user.favorites.add(tweets[5])

    def test_recent_favorites(self):
        "Returns recent favorites from all accounts"
        "UGH, just realised we shouldn't show tweets favorited by private accounts"
        "Not sure we check for that ANYWHERE..."
        pass
