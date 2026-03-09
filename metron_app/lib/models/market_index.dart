class MarketIndex {
  final String name;
  final String symbol;
  final double value;
  final double change;
  final double changePercentage;

  MarketIndex({
    required this.name,
    required this.symbol,
    required this.value,
    required this.change,
    required this.changePercentage,
  });

  bool get isPositive => change >= 0;
}
