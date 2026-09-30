"""Business-day helpers: "today" is decided in Africa/Nairobi (UTC+3), not
on the server's UTC clock."""

from datetime import date, datetime, timezone

from app.time_utils import business_date, business_day_end_utc, business_day_start_utc


def test_late_utc_evening_is_next_business_day():
    # 22:30 UTC on 30 Sep is 01:30 EAT on 1 Oct.
    assert business_date(datetime(2026, 9, 30, 22, 30, tzinfo=timezone.utc)) == date(2026, 10, 1)


def test_naive_timestamps_are_treated_as_utc():
    assert business_date(datetime(2026, 9, 30, 20, 59)) == date(2026, 9, 30)
    assert business_date(datetime(2026, 9, 30, 21, 0)) == date(2026, 10, 1)


def test_business_day_bounds_in_utc():
    assert business_day_start_utc(date(2026, 10, 1)) == datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
    end = business_day_end_utc(date(2026, 10, 1))
    assert end.date() == date(2026, 10, 1) and end.hour == 20 and end.minute == 59
