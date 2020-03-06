#!/usr/bin/env python3

from flask import Flask, g
from thirdparty import bunq

from os import environ
from itertools import islice

app = Flask(__name__)


@app.before_request
def before_request():
    if not hasattr(g, 'init'):
        bunq.init(lambda: environ["BUNQ_API_KEY"])
        g.init = True


@app.route("/balance")
def balance():
    acct = bunq.account('cyburgers')
    balance = acct.balance.value

    events = bunq.events(acct.id_)
    events = map(bunq.show_event, events)
    events = filter(lambda x: x is not None, events)
    events = islice(events, 3)

    msg = f"<h1>{balance}</h1>\n<ul>\n"
    for event in events:
        msg += f"<li>{event}</li>\n"
    msg += '</ul>\n'
    msg += '<p><a href="https://github.com/qguv/cyburgers">source on Github</a></p>'
    return msg


if __name__ == "__main__":
    app.run(port=5957)
