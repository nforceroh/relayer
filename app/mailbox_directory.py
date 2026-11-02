"""Mailbox directory: groups recipient rows into mailboxes and resolves
which mailbox the UI should display.

The interface is one function:

    build_view(rows, selected_mailbox=None) -> dict

It returns the view model the index template needs: mailboxes grouped
from recipient rows, the selected mailbox (falling back to the first
mailbox when the request names one that does not exist), and the rows
for that selection. Callers pass rows from the recipient store; this
module owns every rule about how rows become a directory view.
"""

from collections import OrderedDict


def build_view(rows: list[dict], selected_mailbox: str | None = None) -> dict:
    grouped: OrderedDict[str, list[dict]] = OrderedDict()
    for row in rows:
        grouped.setdefault(row["mailbox"], []).append(row)

    if selected_mailbox not in grouped:
        selected_mailbox = next(iter(grouped), "")

    return {
        "grouped": grouped,
        "selected_mailbox": selected_mailbox,
        "selected_rows": grouped.get(selected_mailbox, []),
    }
