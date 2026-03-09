import '../models/models.dart';

class MockDataService {
  // ── Market Indices ──
  static List<MarketIndex> getMarketIndices() => [
        MarketIndex(
            name: 'NIFTY 50',
            symbol: '^NSEI',
            value: 23465.60,
            change: 187.45,
            changePercentage: 0.81),
        MarketIndex(
            name: 'SENSEX',
            symbol: '^BSESN',
            value: 77298.30,
            change: 612.20,
            changePercentage: 0.80),
        MarketIndex(
            name: 'NIFTY BANK',
            symbol: '^NSEBANK',
            value: 50120.75,
            change: -156.30,
            changePercentage: -0.31),
        MarketIndex(
            name: 'S&P 500',
            symbol: '^GSPC',
            value: 5915.25,
            change: 42.18,
            changePercentage: 0.72),
        MarketIndex(
            name: 'GOLD',
            symbol: 'GC=F',
            value: 9245.00,
            change: 85.00,
            changePercentage: 0.93),
        MarketIndex(
            name: 'USD/INR',
            symbol: 'USDINR=X',
            value: 86.42,
            change: -0.12,
            changePercentage: -0.14),
      ];

  // ── Stock Holdings ──
  static List<StockHolding> getStockHoldings() => [
        StockHolding(
            tradingSymbol: 'RELIANCE',
            quantity: 25,
            averagePrice: 2450.00,
            lastPrice: 2892.35,
            invested: 61250.00,
            dayChange: 32.15,
            dayChangePercentage: 1.12,
            account: 'Zerodha-1',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'TCS',
            quantity: 15,
            averagePrice: 3200.00,
            lastPrice: 3785.60,
            invested: 48000.00,
            dayChange: -18.40,
            dayChangePercentage: -0.48,
            account: 'Zerodha-1',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'INFY',
            quantity: 40,
            averagePrice: 1380.00,
            lastPrice: 1652.90,
            invested: 55200.00,
            dayChange: 24.70,
            dayChangePercentage: 1.52,
            account: 'Zerodha-1',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'HDFCBANK',
            quantity: 30,
            averagePrice: 1520.00,
            lastPrice: 1745.80,
            invested: 45600.00,
            dayChange: 12.30,
            dayChangePercentage: 0.71,
            account: 'Zerodha-2',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'ICICIBANK',
            quantity: 50,
            averagePrice: 920.00,
            lastPrice: 1285.45,
            invested: 46000.00,
            dayChange: 8.65,
            dayChangePercentage: 0.68,
            account: 'Zerodha-2',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'BHARTIARTL',
            quantity: 35,
            averagePrice: 860.00,
            lastPrice: 1648.20,
            invested: 30100.00,
            dayChange: -5.80,
            dayChangePercentage: -0.35,
            account: 'Zerodha-1',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'ITC',
            quantity: 100,
            averagePrice: 340.00,
            lastPrice: 458.75,
            invested: 34000.00,
            dayChange: 3.25,
            dayChangePercentage: 0.71,
            account: 'Zerodha-2',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'WIPRO',
            quantity: 60,
            averagePrice: 380.00,
            lastPrice: 295.40,
            invested: 22800.00,
            dayChange: -4.60,
            dayChangePercentage: -1.53,
            account: 'Zerodha-1',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'SBIN',
            quantity: 80,
            averagePrice: 520.00,
            lastPrice: 788.90,
            invested: 41600.00,
            dayChange: 15.40,
            dayChangePercentage: 1.99,
            account: 'Zerodha-2',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'TATAMOTORS',
            quantity: 45,
            averagePrice: 620.00,
            lastPrice: 985.30,
            invested: 27900.00,
            dayChange: -12.70,
            dayChangePercentage: -1.27,
            account: 'Zerodha-1',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'LT',
            quantity: 12,
            averagePrice: 2780.00,
            lastPrice: 3480.50,
            invested: 33360.00,
            dayChange: 45.30,
            dayChangePercentage: 1.32,
            account: 'Zerodha-2',
            source: 'broker'),
        StockHolding(
            tradingSymbol: 'NIFTYBEES',
            quantity: 200,
            averagePrice: 220.00,
            lastPrice: 268.45,
            invested: 44000.00,
            dayChange: 2.15,
            dayChangePercentage: 0.81,
            exchange: 'NSE',
            account: 'Zerodha-1',
            source: 'broker'),
      ];

  // ── Mutual Funds ──
  static List<MutualFund> getMutualFunds() => [
        MutualFund(
            fund: 'Parag Parikh Flexi Cap Fund',
            tradingSymbol: 'PPFCF-GR',
            quantity: 845.23,
            averagePrice: 52.40,
            lastPrice: 78.65,
            invested: 44290.06,
            lastPriceDate: '2026-03-06',
            account: 'Zerodha-1',
            source: 'broker'),
        MutualFund(
            fund: 'Mirae Asset Large Cap Fund',
            tradingSymbol: 'MALCF-GR',
            quantity: 1230.50,
            averagePrice: 80.20,
            lastPrice: 112.35,
            invested: 98685.10,
            lastPriceDate: '2026-03-06',
            account: 'Zerodha-1',
            source: 'broker'),
        MutualFund(
            fund: 'HDFC Mid-Cap Opportunities',
            tradingSymbol: 'HMCOF-GR',
            quantity: 520.75,
            averagePrice: 125.80,
            lastPrice: 186.40,
            invested: 65510.35,
            lastPriceDate: '2026-03-06',
            account: 'Zerodha-2',
            source: 'broker'),
        MutualFund(
            fund: 'Axis Small Cap Fund',
            tradingSymbol: 'ASCF-GR',
            quantity: 980.10,
            averagePrice: 42.50,
            lastPrice: 68.20,
            invested: 41654.25,
            lastPriceDate: '2026-03-06',
            account: 'Zerodha-2',
            source: 'broker'),
        MutualFund(
            fund: 'SBI Blue Chip Fund',
            tradingSymbol: 'SBBCF-GR',
            quantity: 650.00,
            averagePrice: 62.30,
            lastPrice: 85.90,
            invested: 40495.00,
            lastPriceDate: '2026-03-06',
            account: 'Zerodha-1',
            source: 'broker'),
        MutualFund(
            fund: 'Kotak Equity Opp. Fund',
            tradingSymbol: 'KEOF-GR',
            quantity: 410.80,
            averagePrice: 195.60,
            lastPrice: 282.75,
            invested: 80332.48,
            lastPriceDate: '2026-03-06',
            account: 'Zerodha-1',
            source: 'broker'),
      ];

  // ── SIPs ──
  static List<Sip> getSips() => [
        Sip(
            fund: 'Parag Parikh Flexi Cap Fund',
            tradingSymbol: 'PPFCF-GR',
            instalmentAmount: 10000,
            completedInstalments: 36,
            status: 'ACTIVE',
            nextInstalment: '2026-04-05',
            account: 'Zerodha-1',
            source: 'broker'),
        Sip(
            fund: 'Mirae Asset Large Cap Fund',
            tradingSymbol: 'MALCF-GR',
            instalmentAmount: 5000,
            completedInstalments: 24,
            status: 'ACTIVE',
            nextInstalment: '2026-04-10',
            account: 'Zerodha-1',
            source: 'broker'),
        Sip(
            fund: 'HDFC Mid-Cap Opportunities',
            tradingSymbol: 'HMCOF-GR',
            instalmentAmount: 7500,
            completedInstalments: 18,
            status: 'ACTIVE',
            nextInstalment: '2026-04-15',
            account: 'Zerodha-2',
            source: 'broker'),
        Sip(
            fund: 'Axis Small Cap Fund',
            tradingSymbol: 'ASCF-GR',
            instalmentAmount: 5000,
            completedInstalments: 12,
            status: 'PAUSED',
            nextInstalment: null,
            account: 'Zerodha-2',
            source: 'broker'),
        Sip(
            fund: 'SBI Blue Chip Fund',
            tradingSymbol: 'SBBCF-GR',
            instalmentAmount: 3000,
            completedInstalments: 48,
            status: 'ACTIVE',
            nextInstalment: '2026-04-01',
            account: 'Zerodha-1',
            source: 'broker'),
      ];

  // ── Physical Gold ──
  static List<PhysicalGold> getPhysicalGold() => [
        PhysicalGold(
            type: 'Bars',
            purity: '999',
            weightGrams: 50.0,
            date: '2022-10-15',
            boughtIbjaRatePerGm: 5120.00,
            latestIbjaPricePerGm: 9245.00),
        PhysicalGold(
            type: 'Coins',
            purity: '999',
            weightGrams: 20.0,
            date: '2023-04-20',
            boughtIbjaRatePerGm: 5985.00,
            latestIbjaPricePerGm: 9245.00),
        PhysicalGold(
            type: 'Jewelry',
            purity: '916',
            weightGrams: 85.0,
            date: '2021-06-10',
            boughtIbjaRatePerGm: 4350.00,
            latestIbjaPricePerGm: 8472.00),
        PhysicalGold(
            type: 'Coins',
            purity: '916',
            weightGrams: 10.0,
            date: '2024-01-25',
            boughtIbjaRatePerGm: 5780.00,
            latestIbjaPricePerGm: 8472.00),
      ];

  // ── Fixed Deposits ──
  static List<FixedDeposit> getFixedDeposits() => [
        FixedDeposit(
            bankName: 'HDFC Bank',
            originalAmount: 500000,
            originalInvestmentDate: '2023-01-15',
            interestRate: 7.10,
            depositYear: 3,
            depositMonth: 0,
            maturityDate: 'January 15, 2026',
            currentValue: 614250.00,
            estimatedReturns: 114250.00),
        FixedDeposit(
            bankName: 'SBI',
            originalAmount: 300000,
            reinvestedAmount: 325000,
            originalInvestmentDate: '2022-06-01',
            reinvestedDate: '2023-06-01',
            interestRate: 6.80,
            depositYear: 2,
            maturityDate: 'June 1, 2025',
            currentValue: 370500.00,
            estimatedReturns: 45500.00),
        FixedDeposit(
            bankName: 'ICICI Bank',
            originalAmount: 750000,
            originalInvestmentDate: '2024-03-20',
            interestRate: 7.25,
            depositYear: 5,
            maturityDate: 'March 20, 2029',
            currentValue: 832125.00,
            estimatedReturns: 82125.00),
        FixedDeposit(
            bankName: 'Axis Bank',
            originalAmount: 200000,
            originalInvestmentDate: '2024-09-10',
            interestRate: 7.50,
            depositYear: 1,
            maturityDate: 'September 10, 2025',
            currentValue: 207400.00,
            estimatedReturns: 7400.00),
      ];

  // ── Provident Fund ──
  static List<ProvidentFund> getProvidentFund() => [
        ProvidentFund(
            companyName: 'Tech Corp India',
            startDate: '2018-04-01',
            endDate: '2022-03-31',
            monthlyContribution: 15000,
            closingBalance: 950000,
            monthsWorked: 48,
            totalContribution: 720000,
            interestEarned: 230000,
            isCurrent: false,
            effectiveRate: 8.15),
        ProvidentFund(
            companyName: 'Digital Solutions Ltd',
            startDate: '2022-04-01',
            monthlyContribution: 21000,
            openingBalance: 950000,
            closingBalance: 2185000,
            monthsWorked: 47,
            totalContribution: 987000,
            interestEarned: 248000,
            isCurrent: true,
            effectiveRate: 8.10),
      ];

  // ── Computed Summaries ──
  static Map<String, double> getPortfolioSummary() {
    final stocks = getStockHoldings();
    final mfs = getMutualFunds();
    final sips = getSips();
    final gold = getPhysicalGold();
    final fds = getFixedDeposits();
    final pf = getProvidentFund();

    final stocksInvested = stocks.fold<double>(0, (s, h) => s + h.invested);
    final stocksCurrent = stocks.fold<double>(0, (s, h) => s + h.currentValue);

    final mfInvested = mfs.fold<double>(0, (s, m) => s + m.invested);
    final mfCurrent = mfs.fold<double>(0, (s, m) => s + m.currentValue);

    final goldInvested = gold.fold<double>(0, (s, g) => s + g.investedValue);
    final goldCurrent = gold.fold<double>(0, (s, g) => s + g.currentValue);

    final fdInvested = fds.fold<double>(0, (s, f) => s + f.principal);
    final fdCurrent = fds.fold<double>(0, (s, f) => s + f.currentValue);

    final pfBalance = pf.fold<double>(0, (s, p) => s + p.closingBalance);
    final pfContribution =
        pf.fold<double>(0, (s, p) => s + p.totalContribution);

    final sipMonthly =
        sips.where((s) => s.isActive).fold<double>(0, (s, p) => s + p.instalmentAmount);

    final totalInvested =
        stocksInvested + mfInvested + goldInvested + fdInvested + pfContribution;
    final totalCurrent =
        stocksCurrent + mfCurrent + goldCurrent + fdCurrent + pfBalance;

    return {
      'stocksInvested': stocksInvested,
      'stocksCurrent': stocksCurrent,
      'mfInvested': mfInvested,
      'mfCurrent': mfCurrent,
      'goldInvested': goldInvested,
      'goldCurrent': goldCurrent,
      'fdInvested': fdInvested,
      'fdCurrent': fdCurrent,
      'pfContribution': pfContribution,
      'pfBalance': pfBalance,
      'sipMonthly': sipMonthly,
      'totalInvested': totalInvested,
      'totalCurrent': totalCurrent,
      'totalPnl': totalCurrent - totalInvested,
    };
  }

  // ── Asset Allocation Percentages ──
  static Map<String, double> getAssetAllocation() {
    final summary = getPortfolioSummary();
    final total = summary['totalCurrent']!;
    if (total == 0) return {};
    return {
      'Stocks': (summary['stocksCurrent']! / total) * 100,
      'Mutual Funds': (summary['mfCurrent']! / total) * 100,
      'Gold': (summary['goldCurrent']! / total) * 100,
      'Fixed Deposits': (summary['fdCurrent']! / total) * 100,
      'Provident Fund': (summary['pfBalance']! / total) * 100,
    };
  }
}
