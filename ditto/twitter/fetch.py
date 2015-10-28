# coding: utf-8
import datetime
import json
import pytz
import time

from twython import Twython, TwythonError

from .models import Account, Photo, Tweet, User


# CLASSES HERE:
#
# FetchError
#
# TwitterItemMixin
#   TweetMixin
#   UserMixin
#
# FetchForAccount
#   VerifyForAccount
#   RecentTweetsForAccount
#   FavoriteTweetsForAccount
#
# TwitterFetcher
#   VerifyFetcher
#   RecentTweetsFetcher
#   FavoriteTweetsFetcher
#
# UserFetcher
#
#
# The *Fetcher classes are the ones that should be used externally, like:
#
#   fetcher = RecentTweetsFetcher(screen_name='philgyford')
#   fetcher.fetch()


class FetchError(Exception):
    pass


class TwitterItemMixin(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _api_time_to_datetime(self, api_time, time_format='%a %b %d %H:%M:%S +0000 %Y'):
        """Change a text datetime from the API to a datetime with timezone.
        api_time is a string like 'Wed Nov 15 16:55:59 +0000 2006'.
        """
        return datetime.datetime.strptime(api_time, time_format).replace(
                                                            tzinfo=pytz.utc)


class TweetMixin(TwitterItemMixin):
    """Provides a method for creating/updating a Tweet using data from the API.
    Also used by ingest.TweetIngester()
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save_photos(self, tweet):
        """Takes a Tweet object and creates or updates any photos based on the
        JSON data in its `raw` field.

        Keyword arguments:
        tweet -- The Tweet object. Must have been saved as we need its id.

        Returns:
        Total number of photos for this Tweet (regardless of whether they were
            created or updated).
        """
        photos_count = 0

        try:
            json_data = json.loads(tweet.raw)
        except ValueError as error:
            return photos_count

        try:
            media = json_data['extended_entities']['media']
        except KeyError:
            media = []

        for item in media:
            if 'type' in item and item['type'] == 'photo':
                defaults = {
                    'tweet':        tweet,
                    'twitter_id':   item['id'],
                    'url':          item['media_url_https'],
                    'is_private':   tweet.is_private,
                }

                for size in ['large', 'medium', 'small', 'thumb']:
                    if size in item['sizes']:
                        defaults[size+'_w'] = item['sizes'][size]['w']
                        defaults[size+'_h'] = item['sizes'][size]['h']
                    else:
                        defaults[size+'_w'] = None
                        defaults[size+'_h'] = None

                photo_obj, created = Photo.objects.update_or_create(
                        twitter_id=item['id'],
                        defaults=defaults
                    )
                photos_count += 1

        return photos_count

    def save_tweet(self, tweet, fetch_time, user):
        """Takes a dict of tweet data from the API and creates or updates a
        Tweet object.

        Keyword arguments:
        tweet -- The tweet data.
        fetch_time -- A datetime.
        user -- A User object for whichever User posted this tweet.

        Returns:
        The Tweet object that was created or updated.
        """
        raw_json = json.dumps(tweet)
        try:
            created_at = self._api_time_to_datetime(tweet['created_at'])
        except ValueError:
            # Because the tweets imported from a downloaded archive have a
            # different format for created_at. Of course. Why not?!
            created_at = self._api_time_to_datetime(tweet['created_at'], time_format='%Y-%m-%d %H:%M:%S +0000')

        defaults = {
            'fetch_time':       fetch_time,
            'raw':              raw_json,
            'user':             user,
            'is_private':       user.is_private,
            'created_at':       created_at,
            'permalink':        'https://twitter.com/%s/status/%s' % (
                                            user.screen_name, tweet['id']),
            'title':            tweet['text'].replace('\n', ' ').replace('\r', ' '),
            'summary':          tweet['text'],
            'text':             tweet['text'],
            'twitter_id':       tweet['id'],
            'source':           tweet['source']
        }

        # Some of these are only present in tweets from the API (not in the
        # tweets from the downloaded archive).
        # Some are just not always present, such as coordinates and place stuff.

        if 'favorite_count' in tweet:
            defaults['favorite_count'] = tweet['favorite_count']

        if 'retweet_count' in tweet:
            defaults['retweet_count'] = tweet['retweet_count']

        if 'lang' in tweet:
            defaults['language'] = tweet['lang']

        if 'coordinates' in tweet and tweet['coordinates'] and 'type' in tweet['coordinates']:
            if tweet['coordinates']['type'] == 'Point':
                defaults['latitude'] = tweet['coordinates']['coordinates'][1]
                defaults['longitude'] = tweet['coordinates']['coordinates'][0]
            # TODO: Handle Polygons?

        if 'in_reply_to_screen_name' in tweet and tweet['in_reply_to_screen_name']:
            defaults['in_reply_to_screen_name'] =  tweet['in_reply_to_screen_name']
        else:
            defaults['in_reply_to_screen_name'] = ''

        if 'in_reply_to_status_id' in tweet:
            defaults['in_reply_to_status_id'] = tweet['in_reply_to_status_id']

        if 'in_reply_to_user_id' in tweet:
            defaults['in_reply_to_user_id'] = tweet['in_reply_to_user_id']

        if 'place' in tweet and tweet['place'] is not None:
            if 'attributes' in tweet['place'] and 'street_address' in tweet['place']['attributes']:
                defaults['place_attribute_street_address'] = tweet['place']['attributes']['street_address']
            if 'full_name' in tweet['place']:
                defaults['place_full_name'] = tweet['place']['full_name']
            if 'country' in tweet['place']:
                defaults['place_country'] = tweet['place']['country']

        if 'quoted_status_id' in tweet:
            defaults['quoted_status_id'] = tweet['quoted_status_id']

        tweet_obj, created = Tweet.objects.update_or_create(
                twitter_id=tweet['id'],
                defaults=defaults
            )

        # Create/update any Photos, and update the Tweet's photo_count:
        tweet_obj.photos_count = self.save_photos(tweet=tweet_obj)
        tweet_obj.save()

        return tweet_obj


class UserMixin(TwitterItemMixin):
    "Provides a method for creating/updating a User using data from the API."

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save_user(self, user, fetch_time, extra={}):
        """With Twitter user data from the API, it creates or updates the User
        and returns the User object.

        Keyword arguments:
        user -- A dict of the data about a user from the API's JSON.
        fetch_time -- A datetime.

        Returns the User object.
        """
        raw_json = json.dumps(user)

        # If there's a URL it will be a t.co shortened one.
        # So we go through the entities to find its expanded version.
        if user['url']:
            user_url = user['url']
            if 'url' in user['entities'] and 'urls' in user['entities']['url']:
                for url_dict in user['entities']['url']['urls']:
                    if url_dict['url'] == user['url'] and url_dict['expanded_url'] is not None:
                        user_url = url_dict['expanded_url']
        else:
            user_url = ''

        user_obj, created = User.objects.update_or_create(
            twitter_id=user['id'],
            defaults={
                'fetch_time': fetch_time,
                'raw': raw_json,
                'screen_name': user['screen_name'],
                'name': user['name'],
                'url': user_url,
                'is_private': user['protected'],
                'is_verified': user['verified'],
                'created_at': self._api_time_to_datetime(user['created_at']),
                'description': user['description'] if user['description'] else '',
                'location': user['location'] if user['location'] else '',
                'time_zone': user['time_zone'] if user['time_zone'] else '',
                'profile_image_url': user['profile_image_url'],
                'profile_image_url_https': user['profile_image_url_https'],
                # Note favorites / favourites:
                'favorites_count': user['favourites_count'],
                'followers_count': user['followers_count'],
                'friends_count': user['friends_count'],
                'listed_count': user['listed_count'],
                'statuses_count': user['statuses_count'],
            }
        )

        return user_obj


class FetchForAccount(object):
    """Parent class for children that will call the Twitter API to fetch data
    for a single Account.
    Children should define their own methods for:
        _call_api()
        _save_results()
    and optionally:
        _post_save()
        _post_fetch()

    Use it like:
        account = Account.objects.get(pk=1)
        accountFetcher = RecentTweetsForAccount(account)
        result = accountFetcher.fetch()
    """

    def __init__(self, account):

        self.account = account

        # Will be the Twython object for calling the Twitter API.
        self.api = None

        # Will be the results fetched from the API via Twython.
        self.results = []

        # Will be a list of all the Users/Tweets/etc created/updated:
        self.objects = []

        self.fetch_time = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)

        # What we'll return for each account:
        self.return_value = {}

        # When fetching Tweets, after a query, this will be set as the max_id
        # to use for the next query.
        self.max_id = None

        # When fetching Tweets, this will be set as the highest ID fetched,
        # so it can be used to set account.last_recent_id or
        # account.last_favorite_id when we're done.
        self.last_id = None

        # When fetching Tweets this will be the total amount fetched.
        self.results_count = 0

    def fetch(self):
        if self.account.user:
            self.return_value['account'] = self.account.user.screen_name
        elif self.account.pk:
            self.return_value['account'] = 'Account: %s' % str(self.account)
        else:
            self.return_value['account'] = 'Unsaved Account'

        if self.account.hasCredentials():
            self.api = Twython(
                self.account.consumer_key, self.account.consumer_secret,
                self.account.access_token, self.account.access_token_secret)
            self._fetch_pages()
            self._post_fetch()
        else:
            self.return_value['success'] = False
            self.return_value['message'] = 'Account has no API credentials'

        self.return_value['fetched'] = self.results_count

        return self.return_value

    def _fetch_pages(self):
        try:
            self._call_api()
        except TwythonError as e:
            self.return_value['success'] = False
            self.return_value['message'] = 'Error when calling API: %s' % e
        else:
            # If we've got to the last 'page' of tweet results, we'll receive
            # an empty list from the API.
            if (len(self.results) > 0):
                self._save_results()
                self._post_save()
                if isinstance(self.results, list):
                    # This is nasty. But we only want to do all this stuff
                    # when fetching tweets, rather than verifying credentials.
                    # The former return a list, the latter a dict.
                    if self.last_id is None:
                        self.last_id = self.results[0]['id']
                    # The max_id for the next 'page' of tweets:
                    self.max_id = self.results[-1]['id'] - 1
                    self.results_count += len(self.results)
                    if self._since_id() is None or self.max_id > self._since_id():
                        time.sleep(0.5)
                        self._fetch_pages()
            self.return_value['success'] = True
        return

    def _since_id(self):
        return None

    def _call_api(self):
        """Define in child classes.
        Should call self.api.a_function_name() and set self.results with the
        results.
        """
        raise FetchError("Children of the FetchForAccount class should define their own _call_api() method.")

    def _post_save(self):
        """Can optionally be defined in child classes.
        Do any extra things that need to be done after saving a page of data.
        """
        pass

    def _post_fetch(self):
        """Can optionally be defined in child classes.
        Do any extra things that need to be done after we've fetched all data.
        """
        pass

    def _save_results(self):
        """Define in child classes.
        Should go through self._results() and, probably, call
        self.save_tweet() or self.save_user() for each one.
        """
        self.objects = []


class VerifyForAccount(UserMixin, FetchForAccount):
    """For verifying an Account's API credentials, but ALSO fetches the user
    data for that single Account.
    """

    def __init__(self, account):
        super().__init__(account)

    def _call_api(self):
        """Sets self.results to data for a single Twitter User."""
        self.results = self.api.verify_credentials()

    def _post_save(self):
        "Adds the one User we fetched to the data we'll return from fetch()."
        self.return_value['user'] = self.objects[0]

    def _save_results(self):
        """Creates/updates the user data.
        In other sibling classes this would loop through results and save each
        in turn, but here we only have a single result.
        """
        user = self.save_user(self.results, self.fetch_time)
        self.objects = [user]


class RecentTweetsForAccount(TweetMixin, UserMixin, FetchForAccount):
    """For fetching recent tweets by a single Account."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _since_id(self):
        return self.account.last_recent_id

    def _call_api(self):
        """Sets self.results to be the timeline of tweets for this Account.
        If the account's `last_recent_id` is set, we fetch tweets from that ID
        onwards, up to 200.
        Otherwise we fetch the most recent 200.
        """
        # account.last_recent_id might be None, in which case it's not used in
        # the API call:
        self.results = self.api.get_user_timeline(
                                user_id=self.account.user.twitter_id,
                                include_rts=True,
                                count=200,
                                max_id=self.max_id,
                                since_id=self._since_id())

    def _post_fetch(self):
        """Set the last_recent_id of our Account to the most recent Tweet we
        fetched.
        """
        if self.last_id is not None:
            self.account.last_recent_id = self.last_id
            self.account.save()

    def _save_results(self):
        """Takes the list of tweet data from the API and creates or updates the
        Tweet objects and the posters' User objects.
        Adds each new Tweet object to self.objects.
        """
        for tweet in self.results:
            user = self.save_user(tweet['user'], self.fetch_time)
            tw = self.save_tweet(tweet, self.fetch_time, user)
            self.objects.append(tw)


class FavoriteTweetsForAccount(TweetMixin, UserMixin, FetchForAccount):
    """For fetching tweets favorited by a single Account."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _since_id(self):
        return self.account.last_favorite_id

    def _call_api(self):
        """Sets self.results to be recent tweets favorited by this Account.
        If the account has `last_favorite_id` set, all the favorites since
        that ID are fetched (up to 200).
        Otherwise, the most recent 200 are fetched.
        """
        # account.last_favorite_id might be None, in which case it's not used in
        # the API call:
        self.results = self.api.get_favorites(
                                user_id=self.account.user.twitter_id,
                                count=200,
                                max_id=self.max_id,
                                since_id=self._since_id())

    def _post_fetch(self):
        """Set the last_favorite_id of our Account to the most recent Tweet we
        fetched.
        """
        if self.last_id is not None:
            self.account.last_favorite_id = self.last_id
            self.account.save()

    def _save_results(self):
        """Takes the list of tweet data from the API and creates or updates the
        Tweet objects and the posters' User objects.
        Adds each new Tweet object to self.objects.
        """
        for tweet in self.results:
            user = self.save_user(tweet['user'], self.fetch_time)
            tw = self.save_tweet(tweet, self.fetch_time, user)
            # Associate this tweet with the Account's user:
            self.account.user.favorites.add(tw)
            self.objects.append(tw)


class TwitterFetcher(object):
    """Parent class for children that will call the Twitter API to fetch data
    for one or several Accounts.

    Use like:
        fetcher = ChildFetcher(screen_name='philgyford')
        fetcher.fetch()

    Or, for all accounts:
        fetcher = ChildTwitterFetcher()
        fetcher.fetch()

    Child classes should at least override:
        _get_account_fetcher()
    """

    def __init__(self, screen_name=None):
        """Keyword arguments:
        screen_name -- of the one Account to get, or None for all Accounts.

        Raises:
        FetchError if passed a screen_name there is no Account for.
        """
        # Sets self.accounts:
        self._set_accounts(screen_name)

        # Will be a list of dicts that we return detailing succes/failure
        # results, one dict per account we've fetched for. eg:
        # [ {'account': 'thescreename', 'success': True, 'fetched': 200} ]
        self.return_values = []

    def fetch(self):
        """Fetch data for one or more Accounts.

        Returns:
        A list of dicts, one dict per Account, containing data about
        success/failure.
        """
        for account in self.accounts:
            accountFetcher = self._get_account_fetcher(account)
            return_value = accountFetcher.fetch()
            self._add_to_return_values(return_value)

        return self.return_values

    def _get_account_fetcher(self, account):
        """Should be changed for each child class.
        Should return an instance of a child of TwitterAccountFetcher().

        Keyword arguments:
        account -- An Account object.
        """
        return TwitterAccountFetcher(account)

    def _add_to_return_values(self, return_value):
        """Add return_value to the list in self.return_values."""
        self.return_values.append(return_value)

    def _set_accounts(self, screen_name=None):
        """Sets self.accounts to all Accounts or just one.

        Keyword arguments:
        screen_name -- of the one Account to get, or None for all Accounts.

        Raises:
        FetchError if passed a screen_name there is no Account for, or if none
            of the requested account(s) are marked as is_active.
        """
        if screen_name is None:
            accounts = Account.objects.filter(is_active=True)
            if (len(accounts) == 0):
                raise FetchError("No active Accounts were found to fetch.")
        else:
            try:
                accounts = [Account.objects.get(user__screen_name=screen_name)]
            except Account.DoesNotExist:
                raise FetchError("There is no Account in the database with a screen_name of '%s'" % screen_name)
            else:
                if accounts[0].is_active == False:
                    raise FetchError("The '%s' Account is marked as inactive." % screen_name)

        self.accounts = accounts


class VerifyFetcher(TwitterFetcher):
    """Calls verify_credentials for one/all Accounts.

    If an Account verifies OK, its Twitter User data is fetched and its User
    is created/updated in the databse.

    Usage (or omit screen_name for all Accounts):
        fetcher = VerifyFetcher(screen_name='aScreenName')
        results = fetcher.fetch()
    """

    def _get_account_fetcher(self, account):
        return VerifyForAccount(account)


class RecentTweetsFetcher(TwitterFetcher):
    """Fetches the most recent tweets for one/all Accounts.

    Will fetch tweets since the last fetch.

    Usage (or omit screen_name for all Accounts):
        fetcher = RecentTweetsFetcher(screen_name='aScreenName')
        results = fetcher.fetch()
    """

    def _get_account_fetcher(self, account):
        return RecentTweetsForAccount(account)


class FavoriteTweetsFetcher(TwitterFetcher):
    """Fetches tweets favorited by one/all Accounts, and associate each one
    with the Accounts' twitter User.

    Will fetch favorites since the last fetch.

    Usage (or omit screen_name for all Accounts):
        fetcher = FavoriteTweetsFetcher(screen_name='aScreenName')
        results = fetcher.fetch()
    """

    def _get_account_fetcher(self, account):
        return FavoriteTweetsForAccount(account)

