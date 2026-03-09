import 'package:flutter/material.dart';
import '../models/models.dart';
import 'mock_data_service.dart';

class PortfolioProvider extends ChangeNotifier {
  bool _isLoading = true;
  String? _error;

  List<MarketIndex> _marketIndices = [];
  List<StockHolding> _stocks = [];
  List<MutualFund> _mutualFunds = [];
  List<Sip> _sips = [];
  List<PhysicalGold> _gold = [];
  List<FixedDeposit> _fixedDeposits = [];
  List<ProvidentFund> _providentFund = [];
  Map<String, double> _summary = {};
  Map<String, double> _assetAllocation = {};
  DateTime? _lastUpdated;

  // Getters
  bool get isLoading => _isLoading;
  String? get error => _error;
  List<MarketIndex> get marketIndices => _marketIndices;
  List<StockHolding> get stocks => _stocks;
  List<MutualFund> get mutualFunds => _mutualFunds;
  List<Sip> get sips => _sips;
  List<PhysicalGold> get gold => _gold;
  List<FixedDeposit> get fixedDeposits => _fixedDeposits;
  List<ProvidentFund> get providentFund => _providentFund;
  Map<String, double> get summary => _summary;
  Map<String, double> get assetAllocation => _assetAllocation;
  DateTime? get lastUpdated => _lastUpdated;

  Future<void> loadData() async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    // Simulate network delay
    await Future.delayed(const Duration(milliseconds: 800));

    try {
      _marketIndices = MockDataService.getMarketIndices();
      _stocks = MockDataService.getStockHoldings();
      _mutualFunds = MockDataService.getMutualFunds();
      _sips = MockDataService.getSips();
      _gold = MockDataService.getPhysicalGold();
      _fixedDeposits = MockDataService.getFixedDeposits();
      _providentFund = MockDataService.getProvidentFund();
      _summary = MockDataService.getPortfolioSummary();
      _assetAllocation = MockDataService.getAssetAllocation();
      _lastUpdated = DateTime.now();
      _isLoading = false;
    } catch (e) {
      _error = e.toString();
      _isLoading = false;
    }

    notifyListeners();
  }

  Future<void> refresh() async {
    await loadData();
  }
}
