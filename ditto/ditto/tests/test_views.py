import datetime
from unittest.mock import patch
import pytz

from django.apps import apps
from django.core.urlresolvers import reverse
from django.test import TestCase

from ...flickr import factories as flickrfactories
from ...pinboard import factories as pinboardfactories
from ...twitter import factories as twitterfactories


class DittoViewTests(TestCase):

    def test_home_templates(self):
        "Overall home page uses the correct templates"
        response = self.client.get(reverse('ditto:index'))
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, 'ditto/index.html')
        self.assertTemplateUsed(response, 'ditto/base.html')

    def test_home_context_flickr(self):
        "Overall home page sends correct Flickr data to templates"
        accounts = flickrfactories.AccountFactory.create_batch(3)
        photos_1 = flickrfactories.PhotoFactory.create_batch(3,
                                                        user=accounts[0].user)
        photos_2 = flickrfactories.PhotoFactory.create_batch(3,
                                                        user=accounts[1].user)

        response = self.client.get(reverse('ditto:index'))

        self.assertTrue('flickr_photo_list' in response.context)
        # It shows 4 of all the photos:
        self.assertEqual(len(response.context['flickr_photo_list']), 4)

    def test_home_context_pinboard(self):
        "Overall home page sends correct Pinboard data to templates"
        accounts = pinboardfactories.AccountFactory.create_batch(3)
        bookmarks_1 = pinboardfactories.BookmarkFactory.create_batch(
                                            2, account=accounts[0])
        bookmarks_2 = pinboardfactories.BookmarkFactory.create_batch(
                                            2, account=accounts[1])

        response = self.client.get(reverse('ditto:index'))

        self.assertTrue('pinboard_bookmark_list' in response.context)
        # It shows 3 of all the bookmarks:
        self.assertEqual(len(response.context['pinboard_bookmark_list']), 3)

    def test_home_context_twitter(self):
        "Overall home page sends correct Twitter data to templates"
        accounts = twitterfactories.AccountFactory.create_batch(3)

        # Should be before we generate favoritable_tweets, so we can check
        # twitter_recent_tweet_list only includes these.
        recent_tweets_1 = twitterfactories.TweetFactory.create_batch(
                                                    3, user=accounts[0].user)
        recent_tweets_2 = twitterfactories.TweetFactory.create_batch(
                                                    3, user=accounts[1].user)

        favoritable_tweets = twitterfactories.TweetFactory.create_batch(6)
        for tweet in favoritable_tweets:
            accounts[0].user.favorites.add(tweet)
            accounts[2].user.favorites.add(tweet)

        response = self.client.get(reverse('ditto:index'))

        self.assertIn('twitter_tweet_list', response.context)
        self.assertIn('twitter_favorite_list', response.context)

        self.assertEqual(
            [tweet.pk for tweet in response.context['twitter_tweet_list']],
            [recent_tweets_2[2].pk, recent_tweets_2[1].pk,
                recent_tweets_2[0].pk,]
        )

        self.assertEqual(
            [tweet.pk for tweet in response.context['twitter_favorite_list']],
            [favoritable_tweets[5].pk, favoritable_tweets[4].pk,
                favoritable_tweets[3].pk,]
        )

    def test_home_privacy_flickr(self):
        "Overall home page does not display private Photos"
        public_photo = flickrfactories.PhotoFactory(is_private=False)
        private_photo = flickrfactories.PhotoFactory(is_private=True)
        response = self.client.get(reverse('ditto:index'))

        self.assertEqual(len(response.context['flickr_photo_list']), 1)
        self.assertTrue(response.context['flickr_photo_list'][0].pk,
                                                            public_photo.pk)

    def test_home_privacy_pinboard(self):
        "Overall home page does not display private Bookmarks"
        public_bookmark = pinboardfactories.BookmarkFactory(is_private=False)
        private_bookmark = pinboardfactories.BookmarkFactory(is_private=True)
        response = self.client.get(reverse('ditto:index'))

        self.assertEqual(len(response.context['pinboard_bookmark_list']), 1)
        self.assertTrue(response.context['pinboard_bookmark_list'][0].pk,
                                                            public_bookmark.pk)

    def test_home_privacy_twitter_recent(self):
        "Overall home page does not display private Tweets"
        private_user = twitterfactories.UserFactory(is_private=True)
        public_user = twitterfactories.UserFactory(is_private=False)

        private_account = twitterfactories.AccountFactory(user=private_user)
        public_account = twitterfactories.AccountFactory(user=public_user)

        public_tweet_1 = twitterfactories.TweetFactory(user=public_user)
        private_tweet = twitterfactories.TweetFactory(user=private_user)
        public_tweet_2 = twitterfactories.TweetFactory(user=public_user)

        response = self.client.get(reverse('ditto:index'))

        tweets = response.context['twitter_tweet_list']
        self.assertEqual(len(tweets), 2)
        self.assertEqual(tweets[0].pk, public_tweet_2.pk)
        self.assertEqual(tweets[1].pk, public_tweet_1.pk)

    def test_home_privacy_twitter_favorites(self):
        "Overall home page does not display private favorited Tweets"
        private_user = twitterfactories.UserFactory(is_private=True)
        public_users = twitterfactories.UserFactory.create_batch(2,
                                                            is_private=False)

        favoriting_account = twitterfactories.AccountFactory(
                                                       user=public_users[0])
        private_tweet = twitterfactories.TweetFactory(user=private_user)
        public_tweet = twitterfactories.TweetFactory(user=public_users[1])

        favoriting_account.user.favorites.add(private_tweet)
        favoriting_account.user.favorites.add(public_tweet)

        response = self.client.get(reverse('ditto:index'))

        tweets = response.context['twitter_favorite_list']
        self.assertEqual(len(tweets), 1)
        self.assertEqual(tweets[0].pk, public_tweet.pk)

    def test_home_no_flickr(self):
        "Shouldn't try to get photos if flickr app isn't installed"
        with patch.object(apps, 'is_installed') as mock_method:
            # Fake it so it looks like ditto.flickr isn't installed:
            mock_method.side_effect = lambda x: {
                'ditto.flickr': False,
                'ditto.pinboard': True,
                'ditto.twitter': True,
            }[x]
            response = self.client.get(reverse('ditto:index'))
            self.assertFalse('flickr_photo_list' in response.context)

    def test_home_no_pinboard(self):
        "Shouldn't try to get bookmarks if pinboard app isn't installed"
        with patch.object(apps, 'is_installed') as mock_method:
            # Fake it so it looks like ditto.pinboard isn't installed:
            mock_method.side_effect = lambda x: {
                'ditto.flickr': True,
                'ditto.pinboard': False,
                'ditto.twitter': True,
            }[x]
            response = self.client.get(reverse('ditto:index'))
            self.assertFalse('pinboard_bookmark_list' in response.context)

    def test_home_no_twitter(self):
        "Shouldn't try to get tweets if twitter app isn't installed"
        with patch.object(apps, 'is_installed') as mock_method:
            # Fake it so it looks like ditto.twitter isn't installed:
            mock_method.side_effect = lambda x: {
                'ditto.flickr': True,
                'ditto.pinboard': True,
                'ditto.twitter': False,
            }[x]
            response = self.client.get(reverse('ditto:index'))
            self.assertFalse('twitter_tweet_list' in response.context)

    def test_tag_list_templates(self):
        "Uses the correct templates"
        response = self.client.get(reverse('ditto:tag_list'))
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, 'ditto/tag_list.html')
        self.assertTemplateUsed(response, 'ditto/base.html')

    def test_tag_detail_templates(self):
        "Uses the correct templates"
        bookmark = pinboardfactories.BookmarkFactory.create()
        bookmark.tags.set('fish')
        response = self.client.get(reverse('ditto:tag_detail',
                                                    kwargs={'slug': 'fish'}))
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, 'ditto/tag_detail.html')
        self.assertTemplateUsed(response, 'ditto/base.html')

    def test_tag_detail_context(self):
        "Sends correct data to templates"
        bookmark_1 = pinboardfactories.BookmarkFactory.create(title='Carp')
        bookmark_1.tags.set('Fish', 'carp')
        bookmark_2 = pinboardfactories.BookmarkFactory.create(title='Cod')
        bookmark_2.tags.set('Fish', 'cod')
        bookmark_3 = pinboardfactories.BookmarkFactory.create(title='Dog')
        bookmark_3.tags.set('mammals', 'dog')
        response = self.client.get(reverse('ditto:tag_detail',
                                                    kwargs={'slug': 'fish'}))
        self.assertTrue('tag' in response.context)
        self.assertEqual(response.context['tag'], 'fish')
        self.assertTrue('bookmark_list' in response.context)
        self.assertEqual(len(response.context['bookmark_list']), 2)
        self.assertEqual(response.context['bookmark_list'][0].title, 'Cod')
        self.assertEqual(response.context['bookmark_list'][1].title, 'Carp')

    def test_tag_detail_privacy(self):
        "Does not display private bookmarks"
        bookmark_1 = pinboardfactories.BookmarkFactory.create(is_private=True)
        bookmark_1.tags.set('fish')
        bookmark_2 = pinboardfactories.BookmarkFactory.create(is_private=False)
        bookmark_2.tags.set('fish')
        response = self.client.get(reverse('ditto:tag_detail',
                                                    kwargs={'slug': 'fish'}))
        self.assertTrue('bookmark_list' in response.context)
        self.assertEqual(len(response.context['bookmark_list']), 1)
        self.assertEqual(response.context['bookmark_list'][0].pk, bookmark_2.pk)


class DittoDayArchiveTestCase(TestCase):

    def setUp(self):
        self.url = reverse('ditto:day_archive', kwargs={
            'year': 2015, 'month': '11', 'day': '10',
        })

        self.today = datetime.datetime.strptime(
                    '2015-11-10 12:00:00', '%Y-%m-%d %H:%M:%S'
                ).replace(tzinfo=pytz.utc)
        self.tomorrow = self.today + datetime.timedelta(days=1)
        self.yesterday = self.today - datetime.timedelta(days=1)

        self.bookmark_1 = pinboardfactories.BookmarkFactory.create(
                                                        post_time=self.today)
        self.bookmark_2 = pinboardfactories.BookmarkFactory.create(
                                                    post_time=self.tomorrow)

        tw_account = twitterfactories.AccountFactory.create()
        self.tweet_1 = twitterfactories.TweetFactory.create(
                                    post_time=self.today, user=tw_account.user)
        self.tweet_2 = twitterfactories.TweetFactory.create(
                                post_time=self.tomorrow, user=tw_account.user)

        self.favorite_1 = twitterfactories.TweetFactory.create(
                                                        post_time=self.today)
        self.favorite_2 = twitterfactories.TweetFactory.create(
                                                    post_time=self.tomorrow)
        tw_account.user.favorites.add(self.favorite_1)

    def test_day_templates(self):
        "Day archive page uses the correct templates"
        response = self.client.get(self.url)
        self.assertEquals(response.status_code, 200)
        self.assertTemplateUsed(response, 'ditto/archive_day.html')
        self.assertTemplateUsed(response, 'ditto/base.html')

    def test_day_context(self):
        "Only shows items from the specified day."
        response = self.client.get(self.url)

        self.assertTrue('total_count' in response.context)
        self.assertEqual(3, response.context['total_count'])

        self.assertTrue('pinboard_bookmark_list' in response.context)
        self.assertEqual(1, len(response.context['pinboard_bookmark_list']))
        self.assertEqual(response.context['pinboard_bookmark_list'][0].pk,
                                                            self.bookmark_1.pk)

        self.assertTrue('twitter_tweet_list' in response.context)
        self.assertEqual(1, len(response.context['twitter_tweet_list']))
        self.assertEqual(response.context['twitter_tweet_list'][0].pk,
                                                                self.tweet_1.pk)

        self.assertTrue('twitter_favorite_list' in response.context)
        self.assertEqual(1, len(response.context['twitter_favorite_list']))
        self.assertEqual(response.context['twitter_favorite_list'][0].pk,
                                                            self.favorite_1.pk)

        self.assertTrue('day' in response.context)
        self.assertEqual(response.context['day'], self.today.date())
        self.assertTrue('previous_day' in response.context)
        self.assertEqual(response.context['previous_day'],
                                                        self.yesterday.date())
        self.assertTrue('next_day' in response.context)
        self.assertEqual(response.context['next_day'], self.tomorrow.date())

    def test_day_privacy(self):
        "Doesn't show private items."
        self.bookmark_1.is_private = True
        self.bookmark_1.save()
        self.tweet_1.user.is_private = True
        self.tweet_1.user.save()
        self.favorite_1.user.is_private = True
        self.favorite_1.user.save()

        response = self.client.get(self.url)
        self.assertEqual(0, response.context['total_count'])
        self.assertEqual(0, len(response.context['pinboard_bookmark_list']))
        self.assertEqual(0, len(response.context['twitter_tweet_list']))
        self.assertEqual(0, len(response.context['twitter_favorite_list']))

