class PhysicalGold {
  final String type;
  final String purity;
  final double weightGrams;
  final String date;
  final double boughtIbjaRatePerGm;
  final double latestIbjaPricePerGm;

  PhysicalGold({
    required this.type,
    required this.purity,
    required this.weightGrams,
    required this.date,
    required this.boughtIbjaRatePerGm,
    required this.latestIbjaPricePerGm,
  });

  double get investedValue => weightGrams * boughtIbjaRatePerGm;
  double get currentValue => weightGrams * latestIbjaPricePerGm;
  double get pnl => type == 'Jewelry' ? 0 : currentValue - investedValue;
  double get pnlPercentage =>
      investedValue > 0 && type != 'Jewelry' ? (pnl / investedValue) * 100 : 0;
}
