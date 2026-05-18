# API Notes

## NWS (weather.gov)
- No auth. Requires a `User-Agent` header or requests are rejected.
- `GET /points/{lat},{lon}` → `properties.forecastHourly` is the hourly URL. Cache it.
- Hourly periods include `temperature`, `probabilityOfPrecipitation.value`,
  `relativeHumidity.value`, `windSpeed` (string like "5 mph"), `shortForecast`.
- No apparent-temperature field — "feels like" is computed locally from temp/humidity/wind.

## Metra GTFS-Realtime (deep dive 2026-05-17)
- Realtime trip updates: `GET https://gtfspublic.metrarr.com/gtfs/public/tripupdates?api_token=<TOKEN>`.
  Auth by `api_token` query param. The token lives in the Config sheet, never in code.
- The response is **GTFS-Realtime protobuf** (binary), version `2.0` — not JSON.
  Apps Script has no protobuf library, so `Code.gs` hand-decodes the wire format.
- Static GTFS (`https://schedules.metrarail.com/gtfs/schedule.zip`) confirmed the
  **Northbrook stop_id is `NBROOK`** (MD-N line). The realtime feed uses the same id.
- The feed carries every Metra line's in-service trains (~18 entities in an evening
  sample). Filter `stop_time_update.stop_id == "NBROOK"`.
- `departure` is often absent on a stop_time_update; use `arrival`, fall back to
  `departure`. The time is a Unix epoch (seconds).
- Realtime only lists trains currently in service, so late at night the Northbrook
  Metra set can legitimately be empty.

### Protobuf wire format + GTFS-RT field numbers (verified against a live feed)
- Wire types: 0 = varint, 2 = length-delimited (strings / sub-messages), 1 = 64-bit,
  5 = 32-bit. Tag byte = `(field_number << 3) | wire_type`.
- `FeedMessage`: 1 = header, 2 = entity (repeated)
- `FeedEntity`: 1 = id, 3 = trip_update
- `TripUpdate`: 1 = trip, 2 = stop_time_update (repeated)
- `TripDescriptor`: 1 = trip_id, 2 = start_time, 3 = start_date, 5 = route_id
- `StopTimeUpdate`: 1 = stop_sequence, 2 = arrival, 3 = departure, 4 = stop_id
- `StopTimeEvent`: 2 = time (Unix epoch seconds)
- Epoch values (~1.7e9) fit JS `Number` exactly — no BigInt needed.
- `tests/fixtures/metra-tripupdates.bin` is a captured live feed used as a test
  fixture; it contains two NBROOK MD-N trains (`MD-N_MN2623_V7_AA`,
  `MD-N_MN2620_V7_AA`).
