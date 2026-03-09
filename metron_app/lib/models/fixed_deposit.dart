class FixedDeposit {
  final String bankName;
  final double originalAmount;
  final double? reinvestedAmount;
  final String originalInvestmentDate;
  final String? reinvestedDate;
  final double interestRate;
  final int depositYear;
  final int depositMonth;
  final int depositDay;
  final String maturityDate;
  final double currentValue;
  final double estimatedReturns;

  FixedDeposit({
    required this.bankName,
    required this.originalAmount,
    this.reinvestedAmount,
    required this.originalInvestmentDate,
    this.reinvestedDate,
    required this.interestRate,
    required this.depositYear,
    this.depositMonth = 0,
    this.depositDay = 0,
    required this.maturityDate,
    required this.currentValue,
    required this.estimatedReturns,
  });

  double get principal => reinvestedAmount ?? originalAmount;
}
