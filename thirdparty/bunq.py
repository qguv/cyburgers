#!/usr/bin/env python3

from bunq.sdk.context.api_context import ApiContext
from bunq.sdk.context.api_environment_type import ApiEnvironmentType
from bunq.sdk.context.bunq_context import BunqContext
from bunq.sdk.exception.bunq_exception import BunqException
from bunq.sdk.json.anchor_object_adapter import AnchorObjectAdapter
from bunq.sdk.model.generated import endpoint, object_

from pathlib import Path
from dataclasses import dataclass
import operator

CONTEXTFILE = Path(__file__).parent.parent / ".bunq"
DEVICE_DESCRIPTION = "cloud.guvernator.net"


@dataclass(frozen=True)
class Amount:
    symbols = {'EUR': '€', 'USD': '$', 'GBP': '£'}

    currency: str
    cents: int

    @property
    def currency_symbol(self):
        return self.symbols.get(self.currency)

    @classmethod
    def from_bunq(cls, bunq_amount):
        assert(type(bunq_amount) is object_.Amount)
        digits = ''.join(x for x in bunq_amount.value if x.isdigit())
        cents = int(digits)
        if bunq_amount.value.startswith('-'):
            cents *= -1
        return cls(bunq_amount.currency, cents)

    def __str__(self):
        prefix = self.currency_symbol or f'{self.currency} '
        sign = '-' if self.cents < 0 else ''
        cents = abs(self.cents)
        whole = cents // 100
        partial = cents % 100
        return f'{prefix}{sign}{whole:01}.{partial:02}'

    def __neg__(self):
        return Amount(self.currency, -self.cents)

    def __abs__(self):
        return Amount(self.currency, abs(self.cents))

    def _cmp(self, other, fn):
        if type(self) != type(other):
            return fn(self.cents, other)

        if self.currency != other.currency:
            return NotImplementedError("can't compare different currencies")

        return fn(self.cents, other.cents)

    def __lt__(self, other):
        return self._cmp(other, operator.lt)
    def __le__(self, other):
        return self._cmp(other, operator.le)
    def __eq__(self, other):
        return self._cmp(other, operator.eq)
    def __ne__(self, other):
        return self._cmp(other, operator.ne)
    def __gt__(self, other):
        return self._cmp(other, operator.gt)
    def __ge__(self, other):
        return self._cmp(other, operator.ge)


def init(api_key_fn):
    AnchorObjectAdapter._override_field_map.update({
        'ScheduledPaymentBatch': 'SchedulePaymentBatch',
        'TransferwisePayment': 'TransferwiseTransfer',
    })
    if CONTEXTFILE.exists():
        context = ApiContext.restore(str(CONTEXTFILE))
    else:
        context = ApiContext.create(ApiEnvironmentType.PRODUCTION, api_key_fn(), DEVICE_DESCRIPTION)
        context.save(str(CONTEXTFILE))
    BunqContext.load_api_context(context)


def depaginate(obj, **kwargs):
    res = obj.list(**kwargs)
    while res.value:
        for v in res.value:
            yield v
        try:
            kwargs['params'] = res.pagination.url_params_previous_page
            res = obj.list(**kwargs)
        except BunqException:
            return


def named_account(name):
    try:
        return next(
            a for a in depaginate(endpoint.MonetaryAccountBank)
            if a.status == 'ACTIVE' and a.description == name
        )
    except StopIteration as e:
        raise KeyError(f"No active account with name: {name}.") from e


def account(account_id):
    return endpoint.MonetaryAccountBank.get(account_id).value

def payments(account_id):
    return depaginate(endpoint.Payment, monetary_account_id=account_id)


def events(account_id):
    for event in depaginate(endpoint.Event):
        try:
            if event.object_.get_referenced_object().monetary_account_id == account_id:
                yield event
        except (BunqException, AttributeError):
            print(event.to_json())


def humanize(s):
    return s if any(c.islower() for c in s) else s.title()


def show_event(event):
    try:
        mca = event.object_.MasterCardAction
        desc = mca.description.strip()
        city = mca.city.strip()

        msg = str(Amount.from_bunq(mca.amount_billing))

        if desc:
            msg += ' from ' + humanize(desc)

        if city:
            if city not in desc:
                msg += ' in ' + city.capitalize()

        msg += ' on ' + mca.created.replace(' ', ' at ')
        return msg
    except AttributeError:
        pass

    try:
        rr = event.object_.RequestResponse
        cur = rr.amount_responded.currency
        cur = '€' if cur == 'EUR' else cur + ' '
        msg = cur + rr.amount_responded.value
        msg += ' transferred out'
        if rr.description:
            msg += ' for ' + humanize(rr.description)
        msg += ' on ' + rr.time_responded.replace(' ', ' at ')
        return msg
    except AttributeError:
        pass
