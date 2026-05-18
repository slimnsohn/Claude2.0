# Google Sheet Setup

Create one Google Sheet named **Wall Dashboard Config** with these tabs.

## Tab: `Config`  (two columns; row 1 is the header `Key | Value`)

| Key | Value |
|---|---|
| metra_api_token | (paste your Metra GTFS API token) |
| metra_stop_id | NBROOK |
| nws_lat | 42.0728 |
| nws_lon | -87.7878 |
| nws_forecast_hourly_url | (leave blank — filled by bootstrapNwsUrl_) |
| nws_user_agent | WallDashboard/1.0 (help.sohn@gmail.com) |
| display_start_hour | 6 |
| display_end_hour | 21 |
| weather_flip_hour | 17 |
| weather_end_hour | 19 |
| max_trains | 3 |
| train_window_min | 30 |

## Tab: `AmtrakSchedule`  (header row: `train_num | direction | glenview_time | days`)

Leave the rows empty for now — populated in the trains step.
