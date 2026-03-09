class ProvidentFund {
  final String companyName;
  final String startDate;
  final String? endDate;
  final double monthlyContribution;
  final double openingBalance;
  final double closingBalance;
  final int monthsWorked;
  final double totalContribution;
  final double interestEarned;
  final bool isCurrent;
  final double effectiveRate;

  ProvidentFund({
    required this.companyName,
    required this.startDate,
    this.endDate,
    required this.monthlyContribution,
    this.openingBalance = 0,
    required this.closingBalance,
    required this.monthsWorked,
    required this.totalContribution,
    required this.interestEarned,
    required this.isCurrent,
    required this.effectiveRate,
  });
}
