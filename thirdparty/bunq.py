#!/usr/bin/env python3

from bunq.sdk.context.api_context import ApiContext
from bunq.sdk.context.api_environment_type import ApiEnvironmentType
from bunq.sdk.context.bunq_context import BunqContext
from bunq.sdk.exception.bunq_exception import BunqException
from bunq.sdk.json.anchor_object_adapter import AnchorObjectAdapter
from bunq.sdk.model.generated import endpoint

from pathlib import Path

CONTEXTFILE = Path(__file__).parent.parent / ".bunq"
DEVICE_DESCRIPTION = "cloud.guvernator.net"


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


def depaginate(obj):
    res = obj.list()
    while res.value:
        for v in res.value:
            yield v
        try:
            res = obj.list(res.pagination.url_params_previous_page)
        except BunqException:
            return


def account(name):
    try:
        return next(
            a for a in depaginate(endpoint.MonetaryAccountBank)
            if a.status == 'ACTIVE' and a.description == name
        )
    except StopIteration as e:
        raise KeyError(f"No active account with name: {name}.") from e


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

        cur = mca.amount_billing.currency
        cur = '€' if cur == 'EUR' else cur + ' '
        msg = cur + mca.amount_billing.value

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
