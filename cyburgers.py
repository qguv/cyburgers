#!/usr/bin/env python3

from flask import Flask, g, render_template
from thirdparty import bunq

from os import environ
from itertools import islice

app = Flask(__name__)
account_id = None


@app.before_request
def before_request():
    if not hasattr(g, 'init'):
        bunq.init(lambda: environ["BUNQ_API_KEY"])
        g.init = True


@app.route("/balance")
def balance():
    global account_id
    if account_id:
        acct = bunq.account(account_id)
    else:
        acct = bunq.named_account('cyburgers')
        account_id = acct.id_
    ctx = {}
    ctx['balance'] = bunq.Amount.from_bunq(acct.balance)
    ctx['transactions'] = [format_payment(p) for p in bunq.payments(account_id)]
    return render_template('balance.html', **ctx)


def format_payment(payment):
    t = payment.created[:16]
    amount = bunq.Amount.from_bunq(payment.amount)
    action = f"spent {abs(amount)} for “{payment.description}”" if amount < 0 else f"someone donated {abs(amount)}, thanks!"
    return f"{t}: {action}"


if __name__ == "__main__":
    app.run(port=5957)
