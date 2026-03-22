# Built a dashboard page to show company and sector exposure via stocks, mutual fund and ETFs

## Why

Users must be able to see a detailed dashboard that depicts a complete picture of which companies and sectors they are invested in and how much money they hold in each of them.

## Architecture overview

- Create a new dashboard page at /exposure
- Login is required and PIN is required to access this page.
- If user is not logged in and opens /exposure directly on their browser then take them to the landing page.
- If user is logged in but PIN is not verified, then show the PIN overlay screen same as what we use in portfolio page.
- Can we extract all PIN screens code and make it a standalone UI component so that we can plug it in any other page we want? I'm thinking of code reusability here.
- Add navigation to it in nav menu before "Nifty 50". Name it as "Your Company Exposure".
- Include the exact same nav header that is in portfolio page. Keep list of preferences, my data and settings all intact as options.
- <title> of the page should be "Your Company Exposure — Metron"
- Keep fonts and UI style same as what we have in portfolio page. Minimalist and clean.
- We don't show the "connect broker account" banner and "brokers out of sync" toaster on this page.
- When users log in for the first time and lands up on the portfolio dashboard page, a background fetch starts that fetches all holdings/portfolio data from broker APIs and google sheets. Same data loading flow takes place on manual refresh. This flow fills up the in-memory cache with their portfolio data per user and also syncs data to google sheets.
  - This pre-filled data (warm cache) and our market data (fetched via cron job) are required in the /exposure page.
  - /exposure page will use the data to analyse the company exposure.
  - So if there is no data, show a info banner saying you first need to visit your portfolio dashboard and update your holdings data. Be creative with the info banner. Info banner should have a button that will take them to their dashboard. Explicity mention it to users in the info banner to add broker accounts or manually add entries.
  - Don't show any charts or table if there is no data. 
- If we already have data (stocks/mutual funds/ETFs):
  - /exposure page should build an interactive dashboard with charts and tables.
  - Find all the mutual funds the user invests in (read from cache). Get MFSchemeInfo from MFMarketCache by ISIN. MFSchemeInfo has holdingsUrl. Aggregate all the holdingsUrl for a user and batch call them in an async way.
  - Each holdingsUrl returns an object. "data" array is an array of arrays, inside the object.
    - data[0][1] - Company Name
    - data[0][2] - Sector
    - data[0][5] - Company allocation percentage in the mutual fund.
    - We store these values in cache (per user) and will use them later on.
  - Find all ETFs the user invest in. Aggregate all the ISIN values of all the ETFs. Use the same COMPANY_HOLDINGS_URL_TEMPLATE to do an async batch call. Retrieve the data and store it the same way we do it for mutual funds.
  - Find all the stocks the user invests in. Use token_set_ratio method from the python library rapidfuzz to compare company names.
    - Company name in our portfolio cache can be different from what we get from COMPANY_HOLDINGS_URL. 
    - Like "Tata Consultancy Services Limited" and "TATA CONSULTANCY SERV LT". We know that both of them refers to the same company.
  - The ultimate goal is to build a data structure that will hold companyName, sectorName, allocationPercentage (aggregated) and holdingAmount.
    - holdingAmount is calculated using the allocationPercentage against your total money in stocks, ETFs and mutual funds.
    - Total money means the current value of all the three assets. You can calculate them since we already have our portfolio cache ready.
    - Suppose a user invests in a mutual fund that holds 8% of HDFCBANK stocks. User also has bought HDFCBANK stocks directly. He might also have an ETF that holds HDFCBANK under the hood. We calculate exactly what is the current value of his investment in HDFCBANK done via different asset classes and show that in /exposure page.
    - We show a detailed table that will show company name, value, % of portfolio and funds (MFs and ETFs).
    - Include a horizontal bar graph showing the top 10 holdings.
    - Show pie chart for sector allocations.
    - If you have any other data visualization ideas, share with me.
- Come up with nice chart and table UIs. Think creatively what we can here.
- Add proper spacing between the charts and table.

## Best practices

- The data fetching and storing should work in a complete async manner.
- Write meaningful logs and comments
- Use popular libraries wherever possible. Do not reinvent the wheel.
- Make code reusable and maintainable.
- Go through existing utils/helpers and look if you can reuse code.
- Keep constants all in one place.
- Ask clarifying questions. Don't assume implementation details.
- All the cache you build in this task should be designed per-user and must implement LRU eviction strategy.
- Think of edge cases and ask me about them.
- Don't break any existing functionality in any other flows.

## Validation

- Add new tests
- Verify cache is getting populated and with correct data.
- Run all tests

Act as a senior/lead software engineer and pull off the entire task. You can break this task into small phases and execute them one by one.