class MutualFund {
  final String fund;
  final String tradingSymbol;
  final double quantity;
  final double averagePrice;
  final double lastPrice;
  final double invested;
  final String? lastPriceDate;
  final String account;
  final String source;

  MutualFund({
    required this.fund,
    required this.tradingSymbol,
    required this.quantity,
    required this.averagePrice,
    required this.lastPrice,
    required this.invested,
    this.lastPriceDate,
    required this.account,
    required this.source,
  });

  double get currentValue => quantity * lastPrice;
  double get pnl => currentValue - invested;
  double get pnlPercentage => invested > 0 ? (pnl / invested) * 100 : 0;
}
