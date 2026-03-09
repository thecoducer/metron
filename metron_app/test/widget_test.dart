import 'package:flutter_test/flutter_test.dart';
import 'package:metron_app/services/mock_data_service.dart';

void main() {
  test('Mock data service returns data', () {
    expect(MockDataService.getStockHoldings().isNotEmpty, true);
    expect(MockDataService.getMutualFunds().isNotEmpty, true);
    expect(MockDataService.getSips().isNotEmpty, true);
    expect(MockDataService.getPhysicalGold().isNotEmpty, true);
    expect(MockDataService.getFixedDeposits().isNotEmpty, true);
    expect(MockDataService.getProvidentFund().isNotEmpty, true);
    expect(MockDataService.getMarketIndices().isNotEmpty, true);
  });

  test('Portfolio summary calculates totals', () {
    final summary = MockDataService.getPortfolioSummary();
    expect(summary['totalCurrent']! > 0, true);
    expect(summary['totalInvested']! > 0, true);
    expect(summary.containsKey('totalPnl'), true);
  });

  test('Asset allocation sums to 100%', () {
    final allocation = MockDataService.getAssetAllocation();
    final total = allocation.values.fold<double>(0, (s, v) => s + v);
    expect((total - 100).abs() < 0.1, true);
  });
}
