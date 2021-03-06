import twitter
import file_system_status as status
from markovate import Markovator

import settings
import random
from HTMLParser import HTMLParser


def create_markovated_tweet(tweets, max_length, unwanted_markovations=[]):
    tweets_texts = map(lambda t: t['text'].strip(), tweets)
    markovator = Markovator()
    markovator.parse_sentences(tweets_texts)
    markovation = markovator.markovate()

    unwanted_markovations.extend(tweets_texts)

    count = 0
    while len(markovation) > max_length or markovation in unwanted_markovations:
        markovation = markovator.markovate()
        count += 1
        if count > 20:
            return None

    return markovation


def filter_tweets(tweets):
    return filter_out_mentions(filter_out_links(tweets))


def filter_out_mentions(tweets):
    # TODO This is to be polite, we could keep tweets that mention people that follow us
    return filter(lambda t: not '@' in t['text'], tweets)


def filter_out_links(tweets):
    # Links are almost guaranteed to ruin the context of the markovation
    return filter(lambda t: not ('http://' in t['text'].lower() or
                                 'https://' in t['text'].lower()), tweets)


def filter_out_bad_words(tweets):
    # Might be offensive/inappropriate for humour
    return filter(lambda t: not ('cancer' in t['text'].lower() or
                                 'r.i.p' in t['text'].lower() or
                                 'RIP' in t['text']), tweets)


def reply_to_user(client, user, tweet_id, app_status):
    if user['protected']:
        print("@" + user['screen_name'] + " if your tweets weren't protected I'd be able to say something constructive")
        return

    screen_name = user['screen_name']

    print(screen_name)

    tweets = filter_tweets(twitter.get_tweets(client, screen_name))

    if len(tweets) <= 1:
        print("Not enough tweets")
        fail_reply = "@" + screen_name + " you don't say much, do you?"
        if settings.post_replies:
            twitter.post_tweet(client, fail_reply)
        app_status['latest_reply'] = fail_reply
        return

    tweet_prefix = '@' + screen_name + ' '
    ideal_tweet_length = 140 - len(tweet_prefix)

    best_tweet = create_markovated_tweet(tweets, ideal_tweet_length)

    if best_tweet is not None:
        tweet = tweet_prefix + best_tweet
        if settings.post_replies:
            twitter.post_tweet(client, tweet, reply_to_id=tweet_id)
        encoded = unicode(tweet).encode('utf-8')
        print(encoded + '(' + str(len(encoded)) + ')')
        app_status['latest_reply'] = encoded
    else:
        print('<p>Could not generate reply</p>')
        app_status['latest_reply'] = 'Could not generate'


def process_replies(client):
    app_status = status.load()
    since_id = app_status.get('reply_since_id', -1)

    if since_id:
        mentions = twitter.get_mentions(client, since_id)
    else:
        mentions = twitter.get_mentions(client)

    print(str(len(mentions)) + " mentions since " + str(since_id))

    mentions.reverse()
    for mention in mentions:
        twitter.follow_user(client, mentions[-1]['user']['screen_name'])
        reply_to_user(client, mention['user'], mention['id'], app_status)

        app_status['reply_since_id'] = mention['id']
        app_status['latest_user_replied_to'] = mention['user']['screen_name']

        # Save after each one so if we crash we don't resend replies
        status.save(app_status)


def produce_next_tweet(client, app_status, query=''):
    app_status = status.load()
    tweet_length = 140
    word_count = 0
    query_is_hashtag = False

    if query == '':
        tweets = twitter.get_timeline_tweets(client, 800)
    else:
        tweets = twitter.get_search_tweets(client, 800, query)['statuses']

    tweets = filter_tweets(tweets)

    if len(tweets) <= 1:
        print('Could not generate tweet (not enough eligible tweets)')
        app_status['latest_tweet'] = 'Could not generate tweet (not enough eligible tweets)'
        return

    if query.startswith('#'):
        tweet_length -= len(query)
        query_is_hashtag = True

    recent_tweets = twitter.get_tweets(client, settings.screen_name)
    best_tweet = HTMLParser().unescape(create_markovated_tweet(tweets, tweet_length, map(lambda t: t['text'].strip(), recent_tweets)))

    # Try to avoid tweets that are just hashtags
    for word in best_tweet.split():
        if not word.startswith('#'):
            word_count += 1

    if best_tweet is not None and word_count > 0:
        if query_is_hashtag and query.lower() not in best_tweet.lower():
            best_tweet += ' ' + query  # only add hashtag if not present
        if settings.post_tweets:
            twitter.post_tweet(client, best_tweet)
        encoded = unicode(best_tweet).encode('utf-8')
        print(encoded + '(' + str(len(encoded)) + ')')
        app_status['latest_tweet'] = encoded
    else:
        print('Could not generate tweet')
        app_status['latest_tweet'] = 'Could not generate tweet'

    status.save(app_status)

if __name__ == "__main__":
    print("Started")
    # First, try to authenticate
    client = twitter.auth_client(settings.consumer_key,
                                 settings.consumer_secret,
                                 settings.token_key,
                                 settings.token_secret)

    if client:
        #TODO move reply processing loop here
        process_replies(client)
        if random.randrange(100) < settings.tweet_chance:
            produce_next_tweet(client, status, settings.search_key)

    print("Finished")
