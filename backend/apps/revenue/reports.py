"""Reading the founder's uploaded reports (CSV or Excel) into rows.

Paynow's export and a hand-made payouts sheet differ in layout, so columns are
found by name: the header row is the first of the top 20 rows that has an
amount column and something to match on (a reference or a phone/account).
Pure functions — nothing here touches the database.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

MAX_ROWS = 20000
MAX_BYTES = 10 * 1024 * 1024

COLUMNS = {
    'reference': ('reference', 'merchantreference', 'yourreference', 'ref', 'orderreference', 'invoice', 'invoicenumber',
                  'paymentreference', 'transactionreference', 'ecocashreference', 'txnid', 'txnref', 'receipt',
                  'receiptnumber', 'confirmationcode'),
    'provider_ref': ('paynowreference', 'paynowref', 'paynowid', 'transactionid', 'pollreference', 'gatewayreference'),
    'amount': ('amount', 'amountpaid', 'amountsent', 'total', 'value', 'gross', 'amountusd', 'usd', 'paid'),
    'status': ('status', 'transactionstatus', 'paymentstatus', 'state'),
    'date': ('date', 'datetime', 'created', 'createdat', 'transactiondate', 'time', 'paidon', 'datepaid', 'timestamp'),
    'account': ('phone', 'mobile', 'phonenumber', 'mobilenumber', 'msisdn', 'account', 'accountnumber', 'number',
                'recipient', 'customerphone', 'payer', 'wallet', 'ecocashnumber'),
    'request_id': ('requestid', 'withdrawalid', 'withdrawal', 'request', 'id'),
}
PAID_STATUSES = {'paid', 'awaitingdelivery', 'delivered', 'success', 'successful', 'completed', 'complete', 'approved', 'ok', 'sent'}


class ReportError(ValueError):
    """The file can't be read as a report (shown to the founder)."""


@dataclass
class ReportRow:
    line: int
    amount: Decimal
    reference: str = ''
    provider_ref: str = ''
    account: str = ''
    request_id: str = ''
    status: str = ''
    when: str = ''


def _norm(text) -> str:
    return re.sub(r'[^a-z0-9]', '', str(text or '').lower())


def norm_ref(text) -> str:
    return re.sub(r'\s+', '', str(text or '')).upper()


def parse_amount(raw) -> Optional[Decimal]:
    if raw is None:
        return None
    if isinstance(raw, (int, float, Decimal)):
        return Decimal(str(raw)).quantize(Decimal('0.01'))
    text = re.sub(r'(?i)usd|zwg|zig|\$|,|\s', '', str(raw))
    negative = text.startswith('(') and text.endswith(')')
    text = text.strip('()')
    try:
        value = Decimal(text).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None
    return -value if negative else value


def _cell(value) -> str:
    if isinstance(value, datetime):
        return value.isoformat(sep=' ', timespec='minutes')
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return '' if value is None else str(value).strip()


def _table(name: str, data: bytes) -> list[list]:
    if len(data) > MAX_BYTES:
        raise ReportError('That file is over 10 MB.')
    lower = name.lower()
    if lower.endswith(('.xlsx', '.xlsm')):
        try:
            import openpyxl
            book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001 — any unreadable workbook
            raise ReportError('That Excel file can’t be opened.') from exc
        sheet = book.worksheets[0]
        return [list(r) for _, r in zip(range(MAX_ROWS + 20), sheet.iter_rows(values_only=True))]
    if lower.endswith(('.csv', '.txt')):
        text = data.decode('utf-8-sig', errors='replace')
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t|')
        except csv.Error:
            dialect = csv.excel
        return [row for _, row in zip(range(MAX_ROWS + 20), csv.reader(io.StringIO(text), dialect))]
    raise ReportError('Upload the report as CSV or Excel (.xlsx). For a PDF, enter its total by hand instead.')


def _header(rows: list[list]) -> tuple[int, dict[str, int]]:
    for i, row in enumerate(rows[:20]):
        found: dict[str, int] = {}
        names = [_norm(c) for c in row]
        for key, options in COLUMNS.items():
            for option in options:            # earlier names win (e.g. "amount" over "total")
                if option in names:
                    idx = names.index(option)
                    if idx not in found.values():
                        found[key] = idx
                        break
        if 'amount' in found and ({'reference', 'provider_ref', 'account', 'request_id'} & set(found)):
            return i, found
    raise ReportError('Couldn’t find the columns: the report needs an Amount column and a Reference or Phone column.')


def read_report(name: str, data: bytes, *, paid_only: bool = True) -> dict:
    """{'rows': [ReportRow], 'skipped': n, 'columns': {...}} — rows with an
    amount; with `paid_only`, rows whose status isn't a paid one are skipped."""
    table = _table(name, data)
    head, cols = _header(table)
    rows, skipped = [], 0
    for offset, raw in enumerate(table[head + 1:], start=head + 2):
        get = lambda key: _cell(raw[cols[key]]) if key in cols and cols[key] < len(raw) else ''  # noqa: E731
        amount = parse_amount(raw[cols['amount']] if cols['amount'] < len(raw) else None)
        if amount is None or amount == 0:
            if any(_cell(c) for c in raw):
                skipped += 1
            continue
        status = get('status')
        if paid_only and status and _norm(status) not in PAID_STATUSES:
            skipped += 1
            continue
        rows.append(ReportRow(line=offset, amount=abs(amount), reference=get('reference'), provider_ref=get('provider_ref'),
                              account=get('account'), request_id=get('request_id'), status=status, when=get('date')))
    if not rows:
        raise ReportError('No paid rows found in that report.')
    return {'rows': rows, 'skipped': skipped, 'columns': {k: _cell(table[head][v]) for k, v in cols.items()}}
