#!/usr/bin/env python3

from flask import Flask, render_template
from flask_caching import Cache
from flask_cachecontrol import cache_for
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.wrappers import Response
from thirdparty import bunq

from os import environ
from datetime import datetime
import itertools

config = {
    "CACHE_DEFAULT_TIMEOUT": 60,
    "CACHE_TYPE": "SimpleCache",
}

app = Flask(__name__)
if 'SCRIPT_NAME' in environ:
    app.wsgi_app = DispatcherMiddleware(
        Response('Not Found', status=404),
        {environ['SCRIPT_NAME']: app.wsgi_app},
    )
app.config.from_mapping(config)
cache = Cache(app)
scheduled_account_name = environ.get('BUNQ_SCHEDULED_ACCOUNT_NAME', 'income')
scheduled_id = None
billpay_account_name = environ.get('BUNQ_BILLPAY_ACCOUNT_NAME', 'billpay')
billpay_id = None
show_transactions = environ.get('BUNQ_SHOW_TRANSACTIONS', '').lower() == 'true'

# optional
avail_name = environ.get('BUNQ_AVAIL_NAME')
avail_id = None
avail_target = environ.get('BUNQ_AVAIL_TARGET_CENTS')
if avail_target is not None:
    avail_target = int(avail_target)

bunq_init_done = False


@app.before_request
def before_request():
    global bunq_init_done
    if not bunq_init_done:
        bunq.init(lambda: environ["BUNQ_API_KEY"])
        bunq_init_done = True


@app.route('/ok')
def healthcheck():
    return 'ok', 200


@app.route("/balance")
@cache_for(minutes=1)
@cache.cached()
def balance():
    global scheduled_id
    if scheduled_id:
        scheduled_acct = bunq.account(scheduled_id)
    else:
        scheduled_acct = bunq.named_account(scheduled_account_name)
        scheduled_id = scheduled_acct.id_

    payments = list(bunq.payments(scheduled_id)) if show_transactions else []
    amounts = [bunq.Amount.from_bunq(p.amount) for p in payments] if show_transactions else []

    ctx = {}
    ctx['balance'] = bunq.Amount.from_bunq(scheduled_acct.balance)
    ctx['transactions'] = [format_donation(p) for p in payments]
    ctx['received'] = bunq.Amount('EUR', cents=sum(a.cents for a in amounts if a > 0)) if show_transactions else ctx['balance']
    ctx['spent'] = bunq.Amount('EUR', cents=-sum(a.cents for a in amounts if a < 0))
    ctx['render_time'] = datetime.now()
    return render_template('balance.html', **ctx)


@app.route("/billpay", defaults={'year': 0, 'month': 0})
@app.route("/billpay/<int:year>-<int:month>")
@cache_for(minutes=1)
@cache.cached()
def billpay(year, month):
    global billpay_id
    if billpay_id:
        billpay_acct = bunq.account(billpay_id)
    else:
        billpay_acct = bunq.named_account(billpay_account_name)
        billpay_id = billpay_acct.id_

    ref = datetime(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0) if month and year else datetime.utcnow()
    key_this_month = month_key(ref)
    start_last_month = get_last_month(ref)
    key_last_month = month_key(start_last_month)

    balance = bunq.Amount.from_bunq(billpay_acct.balance)

    # limit payments to the ones since the start of last month (we don't care about the rest)
    # XXX if this is empty, then we'll need to get payments in _descending_ time order
    payments = itertools.takewhile(lambda p: start_last_month < datetime.fromisoformat(p.created), bunq.payments(billpay_id))

    payments_by_month = by_month(payments)
    payment_amounts_by_month = {k: [bunq.Amount.from_bunq(p.amount) for p in ps] for k, ps in payments_by_month.items()}
    net_balances_by_month = {k: bunq.Amount('EUR', cents=sum(amt.cents for amt in amts)) for k, amts in payment_amounts_by_month.items()}

    end_balance_last_month = bunq.Amount('EUR', cents=(
        balance.cents - net_balances_by_month[key_this_month].cents
    ))

    ctx = {}
    ctx['balance'] = balance
    ctx['net_balance_this_month'] = net_balances_by_month[key_this_month]
    ctx['end_balance_last_month'] = end_balance_last_month
    ctx['net_balance_last_month'] = net_balances_by_month[key_last_month]
    ctx['last_month_payments'] = [(format_bill_payment(p), bunq.Amount.from_bunq(p.amount).cents) for p in payments_by_month[key_last_month]]
    ctx['render_time'] = datetime.now()
    return render_template('billpay.html', **ctx)


@app.route("/scheduled")
@cache_for(minutes=1)
@cache.cached()
def scheduled():
    global scheduled_id
    if scheduled_id:
        scheduled_acct = bunq.account(scheduled_id)
    else:
        scheduled_acct = bunq.named_account(scheduled_account_name)
        scheduled_id = scheduled_acct.id_

    # optional
    global avail_id
    if avail_name:
        if avail_id:
            avail_acct = bunq.account(avail_id)
        else:
            avail_acct = bunq.named_account(avail_name)
            avail_id = avail_acct.id_
        avail_balance = bunq.Amount.from_bunq(avail_acct.balance)

    all_payments = [sp for sp in bunq.scheduled_payments(scheduled_id)]
    payments = [sp for sp in all_payments if is_next_month(sp)]
    amounts = [bunq.Amount.from_bunq(p.payment.amount) for p in payments]

    ctx = {}

    income_balance = bunq.Amount.from_bunq(scheduled_acct.balance)
    ctx['outgoing'] = bunq.Amount('EUR', cents=sum(a.cents for a in amounts))
    ctx['num_outgoing'] = len(payments)
    ctx['num_all_outgoing'] = len(all_payments)
    ctx['needed_income'] = bunq.Amount('EUR', cents=-ctx['outgoing'].cents - income_balance.cents)
    if avail_name:
        ctx['needed_avail'] = bunq.Amount('EUR', cents=avail_target - avail_balance.cents)
    ctx['withdraw'] = bunq.Amount('EUR', cents=ctx['needed_income'].cents + (ctx['needed_avail'].cents if avail_name else 0))
    ctx['render_time'] = datetime.now()
    return render_template('scheduled.html', **ctx)


def get_next_month(now):
    return now.replace(
        year=(now.year + 1 if now.month == 12 else now.year),
        month=(1 if now.month == 12 else now.month + 1),
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def get_last_month(now):
    return now.replace(
        year=(now.year - 1 if now.month == 1 else now.year),
        month=(12 if now.month == 1 else now.month - 1),
        day=1,
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def is_next_month(scheduled_payment):
    now = datetime.utcnow()

    start_next_month = get_next_month(now)
    once = scheduled_payment.schedule.recurrence_unit == 'ONCE'
    time_end = scheduled_payment.schedule.time_start if once else scheduled_payment.schedule.time_end
    if time_end is not None:
        time_end = datetime.fromisoformat(time_end)
        if time_end < start_next_month:
            return False

    end_next_month = get_next_month(start_next_month)
    time_start = datetime.fromisoformat(scheduled_payment.schedule.time_start)
    return time_start < end_next_month


def month_key(payment_or_datetime):
    if isinstance(payment_or_datetime, datetime):
        return payment_or_datetime.strftime('%Y-%m')
    return payment_or_datetime.created[:7]


def by_month(payments):
    return {k: list(v) for k, v in itertools.groupby(payments, month_key)}


def format_donation(payment):
    t = payment.created[:16]
    amount = bunq.Amount.from_bunq(payment.amount)
    action = f"spent {abs(amount)} for “{payment.description}”" if amount < 0 else f"someone donated {abs(amount)}, thanks!"
    return f"{t}: {action}"


def format_bill_payment(payment):
    t = payment.created[:16]
    amount = bunq.Amount.from_bunq(payment.amount)
    party = payment._counterparty_alias.label_monetary_account._display_name
    return f"{amount} by {party} for “{payment.description}”"


if __name__ == "__main__":
    app.run(port=5957)
