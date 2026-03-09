class Sip {
  final String fund;
  final String tradingSymbol;
  final double instalmentAmount;
  final String frequency;
  final int instalments;
  final int completedInstalments;
  final String status;
  final String? nextInstalment;
  final String account;
  final String source;

  Sip({
    required this.fund,
    required this.tradingSymbol,
    required this.instalmentAmount,
    this.frequency = 'MONTHLY',
    this.instalments = -1,
    required this.completedInstalments,
    required this.status,
    this.nextInstalment,
    required this.account,
    required this.source,
  });

  double get totalInvested => instalmentAmount * completedInstalments;
  bool get isActive => status == 'ACTIVE';
  bool get isPerpetual => instalments == -1;
}
