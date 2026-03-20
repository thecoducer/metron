# Store ETFs data from brokers in Google Sheets

## Why

ETF holdings come bundled with stock holdings from the broker APIs. We use isETFInstrument(...) check to segregate them in the frontend but we don't store them seperately in their own ETFs sheet in Google sheet. Currently, the ETFs go along with the stocks in the Stocks sheet in Google sheet.

## What

Stock and ETFs holdings should stay on different sheet tabs in user's Google sheets. Our in-memory cache should also follow this segregation while storing the data. The data syncing for ETFs should work the same way we do it for mutual funds and stocks currently.

## Constraints

### Must
- Add ISIN value of the ETFs
- Gold, Silver ETFs are displayed in seperate tables and cards in the UI. We can store all of them in the ETFs sheet.

### Must Not
- ETFs should not stay in Stocks sheet tab.

## Validation

- Add new tests
- Run all tests