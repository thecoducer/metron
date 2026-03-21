# Fetch, compile and store market data in-memory

## Why

1. We need the list of all available mutual funds in the Indian market to display them in a dropdown list in add/edit form for mutual funds in the UI.
2. We will be building a feature in the future where we carry out company exposure analysis. We are going to need the company holdings and sector allocation of mutual funds that an user holds. We will be storing the API endpoint in-memory instead of storing the complete data that the API provides, only fetch the data on-demand.

## Architecture overview

1. Run a cron job daily at 2 am IST that will gather data from APIs and build in-memory cache for easy lookups later on. Use best used library in Python to create and execute the cron job. On every server start/restart, this cron job's task should run at least once so that we don't have empty data in cache until the cron job runs at 2am IST. We won't be using Redis or similar cache systems. We will store data in-memory so handle edge cases pretty well. If you have any confusions, ask me. No LRU/TTL strategy. Data gets refreshed on every cron job run. Below are the steps on how to gather and store data:
   1. https://api.mfapi.in/mf/latest - This API gives us the list of all mutual funds in India along with their latest NAV. API response is going to be huge. So it will take good amount of time to fetch the data. Be cautious and handle carefully.
      1. API returns an array of objects. Focus on only these fields in each object - schemeCode, schemeName, isinGrowth, isinDivReinvestment, nav and date.
      2. Filter out all objects where isinGrowth and isinDivReinvestment both are null. This gives us a clean data with a guarantee that we have at least a field to get the ISIN value.
      3. Prioritize isinGrowth over isinDivReinvestment for getting ISIN value. Replace the isin holder in this URL (https://staticassets.zerodha.com/coin/scheme-portfolio/<isin>.json) with the ISIN value we got and store the link in the following data structure along with all the above retrieved data.
      4. Store all of the above data in different formats as mentioned below:
         1. In-memory map: The key becomes the ISIN value (isin) which maps to an object that holds schemeName, schemeCode, latestNav (nav), navUpdatedDate (date) and holdingsUrl (the edited staticassets zerodha URL) together
         2. In-memory array list: Contains all the schemeName (mutual fund name) strings, sorted lexicographically.
         3. In-memory map: The key becomes schemeName and value is ISIN number. Should we store hash values of schemeName as keys and implement hash based lookups. Will that be more efficient?
2. We already have CRUD functionality using which user can add/edit a mutual fund row. Create a dropdown and show it when user starts typing in the fund name input textbox. Search through the array list of schemeName (mutual fund name) strings. Handle the UI smoothly and use debouncing.
3. The NAV column in the mutual funds table in the UI displays a small, minimal text pointing out the last NAV updated date. Currently, we get this last updated data from the broker API. We don't have the date entry for manually added rows. Store the date along with the lates NAV in google sheets for manual entries and also sync the same fields into the sheet for broker data. Display the date in relative format in the UI for all mutual fund entries.
4. Add a non-required field in mutual fund add/edit form to show the ISIN value stored in Google sheets. We currently do this for stocks and ETFs.
5. Implement API call retry mechanism
6. Mutual fund google sheets already stores ISIN values under "Fund" column. Rename it to "ISIN" and reuse it.
7. Mutual fund names coming from broker APIs can be different than the names in https://api.mfapi.in/mf/latest. The later should take precedence over broker data in such a scenario. Equality can be checked using ISIN. Mutual fund summary rows should use this equality check to group similar contributions added via broker or manually to a particular fund in the same account.

## Best practices

- The data fetching and storing should work in a complete async manner via cron job.
- Dropdown should work on all devices. It should be responsive.
- Write meaningful logs and comments
- Use popular libraries wherever possible. Do not reinvent the wheel.
- Make code reusable and maintainable.
- Go through existing utils/helpers and look if you can reuse code.
- Keep constants all in one place.
- Ask clarifying questions. Don't assume implementation details.
- Be consistent with date formatting

## Validation

- Add new tests
- Verify cache is getting populated and with correct data.
- Run all tests

Act as a senior/lead software engineer and pull off the entire task.