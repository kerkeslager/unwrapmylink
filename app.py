from datetime import datetime
from urllib.parse import urlparse
import json
import os

import redis
import requests

import flask

CURRENT_PATH = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_PATH = os.path.join(CURRENT_PATH, 'templates')
STATIC_PATH = os.path.join(CURRENT_PATH, 'static')

REDIS_CONNECTION = redis.Redis(
    host='localhost',
    port=6379,
    db=0,
)

app = flask.Flask(__name__)

@app.context_processor
def inject_now():
    return {'now': datetime.utcnow()}

def is_valid_url(url):
    try:
        parse_result = urlparse(url)
        return all([
            parse_result.scheme in ['http', 'https'],
            parse_result.netloc,
            parse_result.netloc not in 'unwrapmy.link'
        ])
    except:
        return False

@app.route('/', methods=['GET'])
def index():
    follow = flask.request.args.get('follow')

    redirect_on_complete = flask.request.args.get('redirect-on-complete') == 'on'
    force_follow = flask.request.args.get('force-follow')

    if not follow:
        return flask.render_template('index.html')

    if not is_valid_url(follow):
        return flask.render_template(
            'index.html',
            start=follow,
            errors=['Not a valid URL.'],
        )

    if not force_follow:
        stored = REDIS_CONNECTION.get('url:' + follow)

        if stored:
            result = json.loads(stored)

            if redirect_on_complete:
                return flask.redirect(result['destination'], code=307)

            result['cached'] = True

            return flask.render_template('index.html', **result)

    start = follow
    redirects = []

    try:
        response = requests.get(follow, allow_redirects=False)
    except requests.exceptions.RequestException as e:
        return flask.render_template(
            'index.html',
            start=start,
            errors=['URL returns invalid redirect.'],
        )

    while response.status_code in [301, 302, 303, 307, 308]:
        redirects.append(follow)

        if len(redirects) >= 100:
            return flask.render_template(
                'index.html',
                start=start,
                errors=['Too many redirects (limit = 100).'],
            )

        follow = response.headers['Location']
        try:
            response = requests.get(follow, allow_redirects=False)
        except requests.exceptions.RequestException as e:
            return flask.render_template(
                'index.html',
                start=start,
                errors=['URL returns invalid redirect.'],
            )

    result = {
        'start': start,
        'redirects': redirects,
        'destination': follow
    }

    REDIS_CONNECTION.set('url:' + start, json.dumps(result))

    if redirect_on_complete:
        return flask.redirect(follow, code=307)

    return flask.render_template('index.html', **result)
