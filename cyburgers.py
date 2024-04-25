#!/usr/bin/env python3

from flask import Flask, g, render_template, make_response
from flask_caching import Cache
from flask_cachecontrol import cache_for
from thirdparty import bunq

from os import environ
from itertools import islice
from datetime import datetime

config = {
    "CACHE_DEFAULT_TIMEOUT": 60,
    "CACHE_TYPE": "SimpleCache",
}

app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)
account_id = None


@app.before_request
def before_request():
    if not hasattr(g, 'init'):
        bunq.init(lambda: environ["BUNQ_API_KEY"])
        g.init = True


@app.route("/balance")
@cache_for(minutes=1)
@cache.cached()
def balance():
    global account_id
    if account_id:
        acct = bunq.account(account_id)
    else:
        acct = bunq.named_account('cyburgers')
        account_id = acct.id_

    payments = list(bunq.payments(account_id))
    amounts = [bunq.Amount.from_bunq(p.amount) for p in payments]

    ctx = {}
    ctx['balance'] = bunq.Amount.from_bunq(acct.balance)
    ctx['transactions'] = [format_payment(p) for p in payments]
    ctx['received'] = bunq.Amount('EUR', cents=sum(a.cents for a in amounts if a > 0))
    ctx['spent'] = bunq.Amount('EUR', cents=-sum(a.cents for a in amounts if a < 0))
    ctx['render_time'] = datetime.now()
    return render_template('balance.html', **ctx)


def format_payment(payment):
    t = payment.created[:16]
    amount = bunq.Amount.from_bunq(payment.amount)
    action = f"spent {abs(amount)} for “{payment.description}”" if amount < 0 else f"someone donated {abs(amount)}, thanks!"
    return f"{t}: {action}"


if __name__ == "__main__":
    app.run(port=5957)
