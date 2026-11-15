# NSE bulk and block deals archive

NSE only publishes the latest trading day's bulk and block deals as files:
- https://nsearchives.nseindia.com/content/equities/bulk.csv
- https://nsearchives.nseindia.com/content/equities/block.csv

A scheduled task saves both every weekday evening, so history builds up here:
`YYYY-MM-DD-bulk.csv` and `YYYY-MM-DD-block.csv` (date = the trade date in the file).
