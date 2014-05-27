"""
Colorful user's timeline stream
"""

from __future__ import print_function
from multiprocessing import Process

import os
import os.path
import argparse
import sys
import time
import signal

from twitter.stream import TwitterStream, Timeout, HeartbeatTimeout, Hangup
from twitter.api import *
from twitter.oauth import OAuth, read_token_file
from twitter.oauth_dance import oauth_dance
from twitter.util import printNicely
from dateutil import parser

from .colors import *
from .config import *
from .db import *

g = {}
db = RainbowDB()

def draw(t, keyword=None):
    """
    Draw the rainbow
    """
    # Retrieve tweet
    tid = t['id']
    text = t['text']
    screen_name = t['user']['screen_name']
    name = t['user']['name']
    created_at = t['created_at']
    date = parser.parse(created_at)
    time = date.strftime('%Y/%m/%d %H:%M:%S')

    res = db.tweet_query(tid)
    if not res:
        db.store(tid)
        res = db.tweet_query(tid)
    rid = res[0].rainbow_id

    # Format info
    user = cycle_color(name) + grey(' ' + '@' + screen_name + ' ')
    meta = grey('[' + time + '] [id=' + str(rid) + ']')
    tweet = text.split()
    # Highlight RT
    tweet = map(lambda x: grey(x) if x == 'RT' else x, tweet)
    # Highlight screen_name
    tweet = map(lambda x: cycle_color(x) if x[0] == '@' else x, tweet)
    # Highlight link
    tweet = map(lambda x: cyan(x) if x[0:7] == 'http://' else x, tweet)
    # Highlight search keyword
    if keyword:
        tweet = map(
            lambda x: on_yellow(x) if
            ''.join(c for c in x if c.isalnum()).lower() == keyword.lower()
            else x,
            tweet
        )
    tweet = ' '.join(tweet)

    # Draw rainbow
    line1 = u"{u:>{uw}}:".format(
        u=user,
        uw=len(user) + 2,
    )
    line2 = u"{c:>{cw}}".format(
        c=meta,
        cw=len(meta) + 2,
    )
    line3 = '  ' + tweet

    printNicely(line1)
    printNicely(line2)
    printNicely(line3)
    printNicely('')


def parse_arguments():
    """
    Parse the arguments
    """
    parser = argparse.ArgumentParser(description=__doc__ or "")
    parser.add_argument(
        '-to',
        '--timeout',
        help='Timeout for the stream (seconds).')
    parser.add_argument(
        '-ht',
        '--heartbeat-timeout',
        help='Set heartbeat timeout.',
        default=90)
    parser.add_argument(
        '-nb',
        '--no-block',
        action='store_true',
        help='Set stream to non-blocking.')
    parser.add_argument(
        '-tt',
        '--track-keywords',
        help='Search the stream for specific text.')
    return parser.parse_args()


def authen():
    """
    Authenticate with Twitter OAuth
    """
    # When using rainbow stream you must authorize.
    twitter_credential = os.environ.get(
        'HOME',
        os.environ.get(
            'USERPROFILE',
            '')) + os.sep + '.rainbow_oauth'
    if not os.path.exists(twitter_credential):
        oauth_dance("Rainbow Stream",
                    CONSUMER_KEY,
                    CONSUMER_SECRET,
                    twitter_credential)
    oauth_token, oauth_token_secret = read_token_file(twitter_credential)
    return OAuth(
        oauth_token,
        oauth_token_secret,
        CONSUMER_KEY,
        CONSUMER_SECRET)


def get_decorated_name():
    """
    Beginning of every line
    """
    t = Twitter(auth=authen())
    name = '@' + t.statuses.user_timeline()[-1]['user']['screen_name']
    g['decorated_name'] = grey('[') + grey(name) + grey(']: ')


def home():
    """
    Home
    """
    t = Twitter(auth=authen())
    count = HOME_TWEET_NUM
    if g['stuff'].isdigit():
        count = g['stuff']
    for tweet in reversed(t.statuses.home_timeline(count=count)):
        draw(t=tweet)


def view():
    """
    Friend view
    """
    t = Twitter(auth=authen())
    user = g['stuff'].split()[0]
    if user[0] == '@':
        try:
            count = int(g['stuff'].split()[1])
        except:
            count = HOME_TWEET_NUM
        for tweet in reversed(t.statuses.user_timeline(count=count, screen_name=user[1:])):
            draw(t=tweet)
    else:
        print(red('A name should begin with a \'@\''))
        sys.stdout.write(g['decorated_name'])


def tweet():
    """
    Tweet
    """
    t = Twitter(auth=authen())
    t.statuses.update(status=g['stuff'])


def retweet():
    """
    ReTweet
    """
    t = Twitter(auth=authen())
    try:
        id = int(g['stuff'].split()[0])
        tid = db.rainbow_query(id)[0].tweet_id
        t.statuses.retweet(id=tid,include_entities=False,trim_user=True)
    except:
        print(red('Sorry I can\'t retweet for you.'))
        sys.stdout.write(g['decorated_name'])


def reply():
    """
    Reply
    """
    t = Twitter(auth=authen())
    try:
        id = int(g['stuff'].split()[0])
        tid = db.rainbow_query(id)[0].tweet_id
        user = t.statuses.show(id=tid)['user']['screen_name']
        status = ' '.join(g['stuff'].split()[1:])
        status = '@' + user + ' ' + status.decode('utf-8')
        t.statuses.update(status=status, in_reply_to_status_id=tid)
    except:
        print(red('Sorry I can\'t understand.'))
        sys.stdout.write(g['decorated_name'])


def delete():
    """
    Delete
    """
    t = Twitter(auth=authen())
    try:
        id = int(g['stuff'].split()[0])
        tid = db.rainbow_query(id)[0].tweet_id
        t.statuses.destroy(id=tid)
        print(green('Okay it\'s gone.'))
    except:
        print(red('Sorry I can\'t delete this tweet for you.'))
    sys.stdout.write(g['decorated_name'])


def search():
    """
    Search
    """
    t = Twitter(auth=authen())
    h, w = os.popen('stty size', 'r').read().split()
    if g['stuff'][0] == '#':
        rel = t.search.tweets(q=g['stuff'])['statuses']
        printNicely(grey('*' * int(w) + '\n'))
        print('Newest', SEARCH_MAX_RECORD, 'tweet: \n')
        for i in xrange(5):
            draw(t=rel[i], keyword=g['stuff'].strip())
        printNicely(grey('*' * int(w) + '\n'))
    else:
        print(red('A keyword should be a hashtag (like \'#AKB48\')'))
        sys.stdout.write(g['decorated_name'])


def friend():
    """
    List of friend (following)
    """
    t = Twitter(auth=authen())
    g['friends'] = t.friends.ids()['ids']
    for i in g['friends']:
        screen_name = t.users.lookup(user_id=i)[0]['screen_name']
        user = cycle_color('@' + screen_name)
        print(user, end=' ')
    print('\n')


def follower():
    """
    List of follower
    """
    t = Twitter(auth=authen())
    g['followers'] = t.followers.ids()['ids']
    for i in g['followers']:
        screen_name = t.users.lookup(user_id=i)[0]['screen_name']
        user = cycle_color('@' + screen_name)
        print(user, end=' ')
    print('\n')


def help():
    """
    Help
    """
    usage = '''
    Hi boss! I'm ready to serve you right now!
    ----------------------------------------------------
    "home" will show your timeline. "home 7" will print 7 tweet.
    "view @bob" will show your friend @bob's home.
    "t oops" will tweet "oops" immediately.
    "rt 12345" will retweet to tweet with id "12345".
    "rep 12345 oops" will reply "oops" to tweet with id "12345".
    "del 12345" will delete tweet with id "12345".
    "s #AKB48" will search for "AKB48" and return 5 newest tweet.
    "fr" will list out your following people.
    "fl" will list out your followers.
    "h" will print this help once again.
    "c" will clear the terminal.
    "q" will exit.
    ----------------------------------------------------
    Have fun and hang tight!
    '''
    printNicely(usage)
    sys.stdout.write(g['decorated_name'])


def clear():
    """
    Clear screen
    """
    os.system('clear')


def quit():
    """
    Exit all
    """
    os.kill(g['stream_pid'], signal.SIGKILL)
    sys.exit()


def process(cmd):
    """
    Process switch
    """
    return {
        'home'  : home,
        'view'  : view,
        't'     : tweet,
        'rt'    : retweet,
        'rep'   : reply,
        'del'   : delete,
        's'     : search,
        'fr'    : friend,
        'fl'    : follower,
        'h'     : help,
        'c'     : clear,
        'q'     : quit,
    }.get(cmd, lambda: sys.stdout.write(g['decorated_name']))


def listen(stdin):
    """
    Listen to user's input
    """
    for line in iter(stdin.readline, ''):
        try:
            cmd = line.split()[0]
        except:
            cmd = ''
        # Save cmd to global variable and call process
        g['stuff'] = ' '.join(line.split()[1:])
        process(cmd)()
    stdin.close()


def stream():
    """
    Track the stream
    """
    args = parse_arguments()

    # The Logo
    ascii_art()
    # These arguments are optional:
    stream_args = dict(
        timeout=args.timeout,
        block=not args.no_block,
        heartbeat_timeout=args.heartbeat_timeout)

    # Track keyword
    query_args = dict()
    if args.track_keywords:
        query_args['track'] = args.track_keywords

    # Get stream
    stream = TwitterStream(
        auth=authen(),
        domain='userstream.twitter.com',
        **stream_args)
    tweet_iter = stream.user(**query_args)

    # Iterate over the sample stream.
    for tweet in tweet_iter:
        if tweet is None:
            printNicely("-- None --")
        elif tweet is Timeout:
            printNicely("-- Timeout --")
        elif tweet is HeartbeatTimeout:
            printNicely("-- Heartbeat Timeout --")
        elif tweet is Hangup:
            printNicely("-- Hangup --")
        elif tweet.get('text'):
            draw(t=tweet)


def fly():
    """
    Main function
    """
    get_decorated_name()

    p = Process(target=stream)
    p.start()
    g['stream_pid'] = p.pid
    listen(sys.stdin)
