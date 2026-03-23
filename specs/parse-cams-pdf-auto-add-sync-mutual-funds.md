# Parse CAMS+KFintech PDF and add mutual funds

## Why

This feature will give users to auto-add their mutual fund investments via CAMS+KFintech PDF.

## How

- Create an widget in settings drawer after "sync broker account". Widget should allow to upload the PDF, take in password and account name as input.
- Multi-account support. Each CAMS PDF data should be tied to an account. Show already available account names in the portfolio as a dropdown select in the form. Also an option to add new account.
- Read https://github.com/maharshi-me/investments and understand how exactly they have managed to parse the PDF. I want the exact same functionality.
- Parse the PDF and open up a model where we ask users to verify the mutual fund names. Parsed mutual fund names may not match with our mutual fund names in the market data cache (data we get from mfapi). so users should see a dropdown of all available mutual funds in the MF cache and choose the right one. Initially show the parsed mutual fund name in the text form and keep it editable. Once edit starts trigger the dropdown. Study the way the dropdown functions in portfolio. You can extract out the code to single place and reuse it across different pages/modal.
- After user verifies all parsed data, get the ISIN for those funds and if same ISIN (same mutual fund) already exists in the portfolio, aggregate them together.
- If not present, add new data row to mutual fund table.
- Sync this newly added or updated data to google sheets as data source manual
- Suppose mutual fund XYZ comes from a broker account and already exists in portfolio. In such a case, when the same mutual XYZ comes after this parsing and verification screen, we don't aggregate the two because data source is different. One is broker and the other one is manual. So add a new data row for the manual entry.
- Once a user goes through this flow. The CAMS pdf has transaction history of buy and sells. Show a info nudge near mutual fund table that will take us to a different page (mutual fund transaction history). This page will show graphs, charts and a table for all transaction history chronologically sorted. Show only those mutual funds which were added via the cams upload flow. because only they will have the transaction history.
- show instructions on how to fill the form on cams website to download the pdf. take references https://maharshi-me.github.io/investments/#/settings

### Must
- Normalize data wherever possible
- Proper API formatting
- the transaction details page should not be shown to unauthenticated users
- the transaction details page should not be cached.
- write meaningful comments and logs
- show animations while uploading, parsing. maybe progress bar.
- the graph should show entire history of transaction
- charts that give insights on buy and sell
- make it mobile responsive
- study the theme and color style in portfolio page and apply the same everywhere
- the tables and UI components in portfolio page are mobile responsive. use same components here.
- focus on data correctness, UI/UX
- data sync to google sheets should happen in a non-blocking way
- update the in-memory caches as well

## Validation

- Add new tests
- Run all tests

Act as a senior software engineer and pull off the task.
