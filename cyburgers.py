#!/usr/bin/env python3

from flask import Flask, g
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
    balance = bunq.Amount.from_bunq(acct.balance)
    payments = bunq.payments(account_id)

    msg = f"<h1>current balance: {balance}</h1>\n<ul>\n"
    payments = list(payments)
    if payments:
        msg += '<h2>transactions:</h2>\n'
    for payment in reversed(payments):
        t = payment.created
        amount = bunq.Amount.from_bunq(payment.amount)
        action = f"spent {abs(amount)} for {payment.description}" if amount < 0 else f"someone donated {abs(amount)}, thanks!"
        msg += f"<li>{t[:16]}: {action}</li>\n"
    msg += '</ul>\n'
    msg += '<p><a href="https://github.com/qguv/cyburgers">source on Github</a></p>'
    return msg


if __name__ == "__main__":
    app.run(port=5957)
