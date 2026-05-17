# API Notes

## NWS (weather.gov)
- No auth. Requires a `User-Agent` header or requests are rejected.
- `GET /points/{lat},{lon}` → `properties.forecastHourly` is the hourly URL. Cache it.
- Hourly periods include `temperature`, `probabilityOfPrecipitation.value`,
  `relativeHumidity.value`, `windSpeed` (string like "5 mph"), `shortForecast`.
- No apparent-temperature field — "feels like" is computed locally from temp/humidity/wind.

## Metra (deferred)
- `/gtfs/public/tripupdates` is protobuf binary, not JSON. Notes added when that step starts.
