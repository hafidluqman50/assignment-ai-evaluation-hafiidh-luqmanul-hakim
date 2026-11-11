"""
Modul Tools — implementasi lengkap: pengecekan status tiket dari data mock.
"""

import os
import pandas as pd

MOCK_TICKETS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "mock_tickets.csv")

_tickets_df = None


def _load_tickets():
    global _tickets_df
    if _tickets_df is None:
        _tickets_df = pd.read_csv(MOCK_TICKETS_PATH)
    return _tickets_df


def get_ticket_status(ticket_id: str) -> str:
    """Mencari status tiket berdasarkan ticket_id pada data mock_tickets.csv."""
    df = _load_tickets()
    ticket_id = ticket_id.strip().upper()

    match = df[df["ticket_id"].str.upper() == ticket_id]

    if match.empty:
        return f"Tiket dengan ID '{ticket_id}' tidak ditemukan. Pastikan ID sudah benar, atau hubungi tim IT Support."

    row = match.iloc[0]
    return (
        f"Tiket {row['ticket_id']} ({row['subject']}) atas nama {row['employee_name']} "
        f"saat ini berstatus '{row['status']}'. Terakhir diperbarui pada {row['last_update']}."
    )
