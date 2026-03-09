class StockHolding {
  final String tradingSymbol;
  final int quantity;
  final double averagePrice;
  final double lastPrice;
  final double invested;
  final double dayChange;
  final double dayChangePercentage;
  final String exchange;
  final String account;
  final String source;

  StockHolding({
    required this.tradingSymbol,
    required this.quantity,
    required this.averagePrice,
    required this.lastPrice,
    required this.invested,
    required this.dayChange,
    required this.dayChangePercentage,
    this.exchange = 'NSE',
    required this.account,
    required this.source,
  });

  double get currentValue => quantity * lastPrice;
  double get pnl => currentValue - invested;
  double get pnlPercentage => invested > 0 ? (pnl / invested) * 100 : 0;
}
