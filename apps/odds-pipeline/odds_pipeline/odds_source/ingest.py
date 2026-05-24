"""Historical odds ingest: iterate dates, list events, pull odds, archive."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from dateutil import parser as dtparser

from odds_pipeline import archive, config
from odds_pipeline.odds_source.client import TheOddsApiClient


@dataclass
class PullResult:
    events_processed: int = 0
    events_archived: int = 0
    events_skipped: int = 0
    events_failed: int = 0
    credits_used: int = 0
    errors: list[str] = field(default_factory=list)


def pull_odds_for_sport(
    *,
    client: TheOddsApiClient,
    sport: str,
    date_from: date,
    date_to: date,
    regions: list[str],
    archive_root: str,
    limit: int | None,
) -> PullResult:
    """Iterate days, list events per day, pull odds for each event at commence_time - 5min."""
    sport_key = config.ODDS_API_SPORT_KEYS[sport]
    markets = config.SPORT_MARKETS[sport]
    result = PullResult()

    cur = date_from
    archived_in_sport = 0
    while cur <= date_to:
        list_date = datetime(cur.year, cur.month, cur.day, 12, 0, tzinfo=timezone.utc)
        try:
            events, list_usage = client.get_historical_events(sport_key, list_date)
        except Exception as e:
            result.errors.append(f"events {sport} {cur}: {e}")
            result.events_failed += 1
            cur += timedelta(days=1)
            continue
        result.credits_used += list_usage.last_cost or 0

        for evt in events:
            if limit is not None and archived_in_sport >= limit:
                break
            result.events_processed += 1
            commence = dtparser.isoparse(evt["commence_time"])
            snapshot_time = commence - timedelta(minutes=5)

            if archive.odds_archive_exists(
                root=archive_root, sport=sport,
                event_id=evt["id"], snapshot_time=snapshot_time,
            ):
                result.events_skipped += 1
                continue

            try:
                payload, usage = client.get_historical_event_odds(
                    sport_key=sport_key, event_id=evt["id"],
                    date=snapshot_time, regions=regions, markets=markets,
                )
            except Exception as e:
                result.errors.append(f"odds {sport} {evt['id']}: {e}")
                result.events_failed += 1
                continue

            archive.write_odds(
                root=archive_root, sport=sport,
                event_id=evt["id"], snapshot_time=snapshot_time,
                payload={"_meta": {
                    "odds_api_event": evt, "snapshot_time": snapshot_time.isoformat(),
                    "regions": regions, "markets": markets,
                }, "payload": payload},
            )
            result.events_archived += 1
            archived_in_sport += 1
            result.credits_used += usage.last_cost or 0

        if limit is not None and archived_in_sport >= limit:
            break
        cur += timedelta(days=1)

    return result
